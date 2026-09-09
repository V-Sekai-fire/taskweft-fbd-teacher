defmodule TaskweftFbdTeacher.SpeakingFaces do
  @moduledoc """
  Converts the Speaking_Faces subject zips into per-subject, per-stream zstd
  parquet in normal form, one subject at a time, verifying the Hub's sha256
  before the zip is read and refusing any entry whose bytes are not a PNG or
  a RIFF wav.

  Pictures and audio are written in the shape the dataset viewer renders: a
  struct of `bytes` and `path` rather than a bare binary, with the card
  declaring the column an image or an audio feature. A bare binary column shows
  as a byte count and nothing else.
  """

  alias Explorer.DataFrame, as: DF
  alias Explorer.Series

  @repo "issai/Speaking_Faces"
  @source_sha "eb2f82264d967f761981a683ecae6992a930dfa2"
  @hub "https://huggingface.co"
  @png <<137, 80, 78, 71, 13, 10, 26, 10>>
  @riff "RIFF"
  @streams %{1 => "thermal", 2 => "visual", 3 => "visual_aligned"}
  @stream_dirs %{
    "thr_image" => 1,
    "rgb_image" => 2,
    "rgb_image_aligned" => 3,
    "thr_image_cmd" => 1,
    "rgb_image_cmd" => 2,
    "rgb_image_cmd_aligned" => 3
  }
  @splits %{"Train" => "train", "Valid" => "test", "Test" => "evaluation"}

  def repo, do: @repo
  def source_sha, do: @source_sha
  def streams, do: @streams

  def zips(subject) do
    [
      {"image_only/sub_#{subject}_io.zip", :still},
      {"image_audio/sub_#{subject}_ia.zip", :cmd}
    ]
  end

  def hub_entry(path) do
    dir = Path.dirname(path)
    url = "#{@hub}/api/datasets/#{@repo}/tree/#{@source_sha}/#{dir}"
    %{status: 200, body: body} = Req.get!(url, receive_timeout: 120_000)

    case Enum.find(body, &(&1["path"] == path)) do
      %{"lfs" => %{"oid" => oid, "size" => size}} -> {:ok, %{size: size, sha256: oid}}
      %{"size" => size} -> {:ok, %{size: size, sha256: nil}}
      nil -> {:error, {:absent_on_hub, path}}
    end
  end

  def fetch(path, dest) do
    File.mkdir_p!(Path.dirname(dest))
    {:ok, entry} = hub_entry(path)

    if entry.size == 0 do
      {:empty, entry}
    else
      unless File.exists?(dest) and File.stat!(dest).size == entry.size do
        url = "#{@hub}/datasets/#{@repo}/resolve/#{@source_sha}/#{path}"
        %{status: 200} = Req.get!(url, into: File.stream!(dest), receive_timeout: :infinity)
      end

      sha = file_sha256(dest)

      cond do
        File.stat!(dest).size != entry.size ->
          {:error, {:size_mismatch, path, File.stat!(dest).size, entry.size}}

        entry.sha256 != nil and sha != entry.sha256 ->
          {:error, {:sha_mismatch, path, sha, entry.sha256}}

        true ->
          {:ok, %{path: dest, size: entry.size, sha256: sha}}
      end
    end
  end

  def file_sha256(path) do
    path
    |> File.stream!([], 4_194_304)
    |> Enum.reduce(:crypto.hash_init(:sha256), &:crypto.hash_update(&2, &1))
    |> :crypto.hash_final()
    |> Base.encode16(case: :lower)
  end

  def with_zip(path, fun) do
    {:ok, handle} = :zip.zip_open(String.to_charlist(path), [:memory])

    try do
      fun.(handle)
    after
      :zip.zip_close(handle)
    end
  end

  def entries(handle) do
    {:ok, list} = :zip.zip_list_dir(handle)

    for {:zip_file, name, _info, _comment, _offset, _csize} <- list,
        name = to_string(name),
        not String.ends_with?(name, "/"),
        do: name
  end

  def get(handle, name) do
    {:ok, {_name, bin}} = :zip.zip_get(String.to_charlist(name), handle)
    bin
  end

  @doc "Parses one entry name into its key, or returns the reason it is refused."
  def parse(name) do
    with [_root, "trial_" <> trial_dir, stream_dir, file] <- String.split(name, "/"),
         {:ok, trial} <- int(trial_dir),
         {:ok, fields} <- fields(Path.rootname(file)),
         {:ok, key} <- key(Path.extname(file), stream_dir, fields) do
      if key.trial == trial, do: {:ok, key}, else: {:error, {:trial_dir_disagrees, name}}
    else
      {:error, reason} -> {:error, {reason, name}}
      _ -> {:error, {:unrecognised_path, name}}
    end
  end

  defp key(".png", stream_dir, [sub, trial, 1, pos, frame, stream]) do
    stream_of(stream_dir, stream, %{kind: :still, sub: sub, trial: trial, pos: pos, frame: frame})
  end

  defp key(".png", stream_dir, [sub, trial, 2, pos, cmd, frame, stream]) do
    stream_of(stream_dir, stream, %{
      kind: :cmd,
      sub: sub,
      trial: trial,
      pos: pos,
      cmd: cmd,
      frame: frame
    })
  end

  defp key(".wav", "mic" <> _, [sub, trial, 2, pos, cmd, mic]) do
    {:ok, %{kind: :utterance, sub: sub, trial: trial, pos: pos, cmd: cmd, mic: mic}}
  end

  defp key(_, _, _), do: {:error, :unrecognised_fields}

  defp stream_of(stream_dir, stream, key) do
    case Map.fetch(@stream_dirs, stream_dir) do
      {:ok, ^stream} -> {:ok, Map.put(key, :stream, stream)}
      _ -> {:error, :stream_dir_disagrees}
    end
  end

  defp fields(stem) do
    stem
    |> String.split("_")
    |> Enum.reduce_while({:ok, []}, fn part, {:ok, acc} ->
      case int(part) do
        {:ok, n} -> {:cont, {:ok, [n | acc]}}
        error -> {:halt, error}
      end
    end)
    |> case do
      {:ok, rev} -> {:ok, Enum.reverse(rev)}
      error -> error
    end
  end

  defp int(s) do
    case Integer.parse(s) do
      {n, ""} -> {:ok, n}
      _ -> {:error, :not_an_integer}
    end
  end

  def check_magic(%{kind: :utterance}, <<@riff, _::binary>>), do: :ok
  def check_magic(%{kind: :utterance}, _), do: {:error, :not_a_wav}
  def check_magic(_, <<@png, _::binary>>), do: :ok
  def check_magic(_, _), do: {:error, :not_a_png}

  @doc """
  Reads every entry of one zip into parquet files under `out/<split>/...` and
  returns the per-group counts. Refuses on the first entry that does not parse
  or whose bytes carry the wrong magic.
  """
  def convert_zip(zip_path, subject, split, out) do
    with_zip(zip_path, fn handle ->
      names = entries(handle)

      keyed =
        Enum.map(names, fn name ->
          case parse(name) do
            {:ok, key} ->
              if key.sub != subject, do: throw({:refused, {:subject_disagrees, name}})
              {name, key}

            {:error, reason} ->
              throw({:refused, reason})
          end
        end)

      keyed
      |> Enum.group_by(fn {_name, key} -> group(key) end)
      |> Enum.sort()
      |> Enum.map(fn {group, members} ->
        rows =
          Enum.map(members, fn {name, key} ->
            bin = get(handle, name)

            case check_magic(key, bin) do
              :ok -> {key, bin}
              {:error, why} -> throw({:refused, {why, name}})
            end
          end)

        path = write_group(group, rows, subject, split, out)
        {group, %{rows: length(rows), path: path, bytes: File.stat!(path).size}}
      end)
    end)
  catch
    {:refused, reason} -> {:error, reason}
  end

  defp group(%{kind: :still, trial: t, stream: s}), do: {:still, s, t}
  defp group(%{kind: :cmd, trial: t, stream: s}), do: {:cmd, s, t}
  defp group(%{kind: :utterance, trial: t}), do: {:audio, 0, t}

  defp write_group({rel, stream, trial}, rows, subject, split, out) do
    dir =
      case rel do
        :audio -> Path.join([out, split, "audio"])
        _ -> Path.join([out, split, to_string(rel), Map.fetch!(@streams, stream)])
      end

    File.mkdir_p!(dir)
    path = Path.join(dir, "sub_#{pad(subject)}_trial_#{trial}.parquet")
    df = frame(rel, rows)
    :ok = DF.to_parquet(df, path, compression: {:zstd, 3})
    path
  end

  defp frame(:still, rows) do
    DF.new(
      sub_id: col(rows, & &1.sub, {:s, 16}),
      trial: col(rows, & &1.trial, {:s, 8}),
      position: col(rows, & &1.pos, {:s, 8}),
      frame: col(rows, & &1.frame, {:s, 32}),
      image: media(rows, "png")
    )
  end

  defp frame(:cmd, rows) do
    DF.new(
      sub_id: col(rows, & &1.sub, {:s, 16}),
      trial: col(rows, & &1.trial, {:s, 8}),
      position: col(rows, & &1.pos, {:s, 8}),
      command: col(rows, & &1.cmd, {:s, 16}),
      frame: col(rows, & &1.frame, {:s, 32}),
      image: media(rows, "png")
    )
  end

  defp frame(:audio, rows) do
    DF.new(
      sub_id: col(rows, & &1.sub, {:s, 16}),
      trial: col(rows, & &1.trial, {:s, 8}),
      position: col(rows, & &1.pos, {:s, 8}),
      command: col(rows, & &1.cmd, {:s, 16}),
      mic: col(rows, & &1.mic, {:s, 8}),
      audio: media(rows, "wav")
    )
  end

  defp col(rows, getter, dtype) do
    Series.from_list(Enum.map(rows, fn {key, _} -> getter.(key) end), dtype: dtype)
  end

  @doc """
  The viewer's media shape: `{bytes, path}`. The path names the entry inside the
  source archive, so a row still says where its picture came from.
  """
  def media(rows, ext) do
    Series.from_list(
      Enum.map(rows, fn {key, bin} -> %{"bytes" => bin, "path" => name_of(key, ext)} end),
      dtype: {:struct, [{"bytes", :binary}, {"path", :string}]}
    )
  end

  defp name_of(%{kind: :still} = k, ext),
    do: "#{k.sub}_#{k.trial}_1_#{k.pos}_#{k.frame}_#{k.stream}.#{ext}"

  defp name_of(%{kind: :cmd} = k, ext),
    do: "#{k.sub}_#{k.trial}_2_#{k.pos}_#{k.cmd}_#{k.frame}_#{k.stream}.#{ext}"

  defp name_of(%{kind: :utterance} = k, ext),
    do: "#{k.sub}_#{k.trial}_2_#{k.pos}_#{k.cmd}_#{k.mic}.#{ext}"

  def pad(subject), do: String.pad_leading(Integer.to_string(subject), 3, "0")

  @doc "The subjects table from the Hub's metadata CSV, with the workspace's split names."
  def subjects(cache_dir) do
    dest = Path.join(cache_dir, "subjects.csv")
    {:ok, _} = fetch("metadata/subjects.csv", dest)
    df = DF.from_csv!(dest)

    for row <- DF.to_rows(df) do
      %{
        sub_id: row["Sub_ID"],
        split: Map.fetch!(@splits, row["Split"]),
        age: row["Age"],
        gender: row["Gender"],
        ethnicity: row["Ethnicity"],
        accessories: [
          {1, accessories(row["Acc_Trial_1"])},
          {2, accessories(row["Acc_Trial_2"])}
        ]
      }
    end
  end

  defp accessories("None"), do: []
  defp accessories(s), do: String.split(s, ";")

  @doc "Writes subjects.parquet and subject_accessories.parquet in normal form."
  def write_subjects(subjects, out) do
    File.mkdir_p!(out)

    subjects_df =
      DF.new(
        sub_id: Series.from_list(Enum.map(subjects, & &1.sub_id), dtype: {:s, 16}),
        split: Series.from_list(Enum.map(subjects, & &1.split), dtype: :category),
        age: Series.from_list(Enum.map(subjects, & &1.age), dtype: {:s, 8}),
        gender: Series.from_list(Enum.map(subjects, & &1.gender), dtype: :category),
        ethnicity: Series.from_list(Enum.map(subjects, & &1.ethnicity), dtype: :category)
      )

    acc =
      for s <- subjects,
          {trial, names} <- s.accessories,
          name <- names,
          do: {s.sub_id, trial, name}

    acc_df =
      DF.new(
        sub_id: Series.from_list(Enum.map(acc, &elem(&1, 0)), dtype: {:s, 16}),
        trial: Series.from_list(Enum.map(acc, &elem(&1, 1)), dtype: {:s, 8}),
        accessory: Series.from_list(Enum.map(acc, &elem(&1, 2)), dtype: :category)
      )

    p1 = Path.join(out, "subjects.parquet")
    p2 = Path.join(out, "subject_accessories.parquet")
    :ok = DF.to_parquet(subjects_df, p1, compression: {:zstd, 3})
    :ok = DF.to_parquet(acc_df, p2, compression: {:zstd, 3})
    %{subjects: DF.n_rows(subjects_df), accessories: DF.n_rows(acc_df), paths: [p1, p2]}
  end

  @doc """
  Fetches, verifies and converts one subject's zips, writes the subject's
  manifest and deletes the zips. A subject with a manifest is skipped by
  `--resume`; an empty zip is named in the manifest, never skipped silently.
  """
  def convert_subject(subject, split, out, cache_dir) do
    started = System.monotonic_time(:millisecond)

    results =
      for {path, _kind} <- zips(subject) do
        dest = Path.join(cache_dir, path)

        case fetch(path, dest) do
          {:empty, entry} ->
            {path, %{empty: true, size: entry.size, sha256: entry.sha256, groups: %{}}}

          {:ok, got} ->
            case convert_zip(dest, subject, split, out) do
              {:error, reason} ->
                throw({:refused, path, reason})

              groups ->
                File.rm!(dest)

                {path,
                 %{
                   empty: false,
                   size: got.size,
                   sha256: got.sha256,
                   groups: Map.new(groups, fn {g, v} -> {group_name(g), v} end)
                 }}
            end

          {:error, reason} ->
            throw({:refused, path, reason})
        end
      end

    manifest = %{
      subject: subject,
      split: split,
      source: %{repo: @repo, sha: @source_sha},
      zips: Map.new(results),
      rows:
        results
        |> Enum.flat_map(fn {_p, z} -> Map.values(z.groups) end)
        |> Enum.map(& &1.rows)
        |> Enum.sum(),
      bytes:
        results
        |> Enum.flat_map(fn {_p, z} -> Map.values(z.groups) end)
        |> Enum.map(& &1.bytes)
        |> Enum.sum(),
      wall_s: (System.monotonic_time(:millisecond) - started) / 1000
    }

    dir = Path.join(out, "manifest")
    File.mkdir_p!(dir)
    File.write!(Path.join(dir, "sub_#{pad(subject)}.json"), Jason.encode!(manifest, pretty: true))
    {:ok, manifest}
  catch
    {:refused, path, reason} -> {:error, {path, reason}}
  end

  @doc """
  The dataset card. The `dataset_info` block declares which columns are pictures
  and which are audio, which is how the viewer knows to render them rather than
  print a byte count; the `configs` block gives one config per relation with the
  three splits.
  """
  def card(repo, counts) do
    """
    ---
    license: cc-by-4.0
    task_categories:
    - image-classification
    - audio-classification
    tags:
    - multimodal
    - thermal
    - speaking-faces
    - weftspun
    configs:
    #{configs(counts)}dataset_info:
      features:
      - name: sub_id
        dtype: int16
      - name: trial
        dtype: int8
      - name: position
        dtype: int8
      - name: image
        dtype: image
      - name: audio
        dtype: audio
    ---

    # #{repo |> String.split("/") |> List.last()}

    The SpeakingFaces set converted to the workspace's form: per subject, per
    trial and per stream, one ZStandard parquet in Essential Tuple Normal Form,
    with the picture bytes in the column rather than a path beside it. Streams
    are `thermal` (464x348), `visual` (768x512) and `visual_aligned`, over nine
    camera positions and two sessions; the command session carries the trimmed
    audio from both microphones.

    Three splits, held out by subject: `train` is the authors' Train, `test`
    their Valid, and `evaluation` their Test, so no subject appears in more than
    one. The population is narrow, 90 Asian, 46 Caucasian and 6 Black subjects
    aged 20 to 64, which is why this set validates a fit rather than serving as
    an identity prior.

    Source: `issai/Speaking_Faces` at `#{@source_sha}`, CC BY 4.0 on the
    project page with MIT code at `IS2AI/SpeakingFaces`. Cite
    doi:10.3390/s21103465.
    """
  end

  defp configs(counts) do
    for {name, splits} <- counts, into: "" do
      "- config_name: #{name}
  data_files:
" <>
        for({split, dir} <- splits, into: "", do: "  - split: #{split}
    path: #{dir}/**/*.parquet
")
    end
  end

  defp group_name({rel, 0, trial}), do: "#{rel}/trial_#{trial}"

  defp group_name({rel, stream, trial}),
    do: "#{rel}/#{Map.fetch!(@streams, stream)}/trial_#{trial}"
end
