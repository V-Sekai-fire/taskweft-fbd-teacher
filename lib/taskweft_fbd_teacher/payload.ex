defmodule TaskweftFbdTeacher.Payload do
  @moduledoc """
  Whether a published dataset carries its own payload.

  A path column is not the data. The publisher uploads with the writer's
  scratch tree ignored and deletes any copy already on the Hub, so a column
  holding `rows/<template>/<seed>/rank3.fbd` published scores for a diagram the
  dataset did not contain. This reads a published dataset back and refuses
  three shapes: a path where the payload should be, media bytes the viewer
  cannot render, and a card promising a column that is not there.
  """

  alias Explorer.DataFrame, as: DF
  alias Explorer.Series

  @hub "https://huggingface.co"

  @payload_extensions ~w(fbd xml json png jpg jpeg gif webp glb usda usdc usdz
                         npy npz ply obj stl wav mp3 flac mkv mov mp4 lot svg
                         parquet safetensors gguf onnx)

  @magic [
    {"PNG", <<137, 80, 78, 71, 13, 10, 26, 10>>},
    {"JPEG", <<255, 216, 255>>},
    {"GIF", "GIF8"},
    {"RIFF", "RIFF"},
    {"Matroska", <<26, 69, 223, 163>>},
    {"OggS", "OggS"},
    {"glTF", "glTF"}
  ]

  defmodule Finding do
    @moduledoc "One reason a dataset is refused, naming the table and column it is in."
    defstruct [:kind, :repo, :table, :column, :detail]
  end

  @doc "Every file the dataset holds, by path."
  def files(repo) do
    url = "#{@hub}/api/datasets/#{repo}/tree/main?recursive=1"

    case Req.get(url, receive_timeout: 120_000) do
      {:ok, %{status: 200, body: entries}} when is_list(entries) ->
        {:ok, MapSet.new(entries, & &1["path"])}

      {:ok, %{status: status}} ->
        {:error, {:tree, status}}

      {:error, why} ->
        {:error, {:tree, why}}
    end
  end

  @doc """
  The card's declared features, from the `dataset_info` block of its front
  matter. A card without one declares nothing, which is itself a finding when
  the dataset carries media.
  """
  def declared_features(repo) do
    url = "#{@hub}/datasets/#{repo}/raw/main/README.md"

    with {:ok, %{status: 200, body: text}} <- Req.get(url, receive_timeout: 120_000),
         {:ok, front} <- front_matter(text),
         {:ok, yaml} <- YamlElixir.read_from_string(front) do
      {:ok, features_of(yaml)}
    else
      {:ok, %{status: status}} -> {:error, {:card, status}}
      other -> other
    end
  end

  defp front_matter(text) do
    case String.split(text, ~r/^---\s*$/m, parts: 3) do
      ["", front, _rest] -> {:ok, front}
      _ -> {:error, :no_front_matter}
    end
  end

  defp features_of(%{"dataset_info" => info}) when is_map(info) do
    info |> Map.get("features", []) |> feature_map()
  end

  defp features_of(%{"dataset_info" => [first | _]}), do: features_of(%{"dataset_info" => first})
  defp features_of(_), do: %{}

  defp feature_map(features) when is_list(features) do
    for %{"name" => name} = f <- features, into: %{}, do: {name, Map.get(f, "dtype", "unknown")}
  end

  defp feature_map(_), do: %{}

  @media_dtypes ~w(image audio video)

  def media_dtype?(dtype), do: dtype in @media_dtypes

  @doc "Whether a value looks like a path to a payload rather than the payload."
  def payload_path?(value) when is_binary(value) do
    trimmed = String.trim(value)

    with false <- trimmed == "",
         false <- String.contains?(trimmed, ["\n", " "]),
         [_ | _] = parts <- String.split(trimmed, "."),
         ext when ext != trimmed <- parts |> List.last() |> String.downcase() do
      ext in @payload_extensions
    else
      _ -> false
    end
  end

  def payload_path?(_), do: false

  @doc "The media kind these bytes start with, or nil."
  def magic_of(<<>>), do: nil

  def magic_of(bytes) when is_binary(bytes) do
    Enum.find_value(@magic, fn {name, prefix} ->
      if String.starts_with?(bytes, prefix), do: name
    end)
  end

  def magic_of(_), do: nil

  @doc """
  Reads one parquet and reports what it finds. `files` is the dataset's file
  set, used to tell a dangling path from one that merely points beside the
  parquet instead of into it.
  """
  def check_table(repo, table, path, files, features) do
    df = DF.from_parquet!(path)

    Enum.flat_map(DF.names(df), fn column ->
      series = DF.pull(df, column)
      values = series |> Series.head(200) |> Series.to_list()
      column_findings(repo, table, column, series, values, files, features)
    end)
  end

  defp column_findings(repo, table, column, series, values, files, features) do
    cond do
      Series.dtype(series) == :binary ->
        bare_media(repo, table, column, values, features)

      true ->
        path_findings(repo, table, column, values, files)
    end
  end

  defp bare_media(repo, table, column, values, features) do
    case values |> Enum.find(&(is_binary(&1) and magic_of(&1) != nil)) |> magic_of() do
      nil ->
        []

      kind ->
        if media_dtype?(Map.get(features, column, "unknown")) do
          []
        else
          [
            %Finding{
              kind: :bare_media,
              repo: repo,
              table: table,
              column: column,
              detail:
                "holds #{kind} bytes as a bare binary; the viewer shows a byte count. " <>
                  "Make it a struct of bytes and path and declare the feature in the card."
            }
          ]
        end
    end
  end

  defp path_findings(repo, table, column, values, files) do
    paths = Enum.filter(values, &payload_path?/1)

    case paths do
      [] ->
        []

      [example | _] ->
        dangling = Enum.reject(paths, &MapSet.member?(files, String.trim_leading(&1, "./")))

        kind = if dangling == [], do: :payload_beside, else: :dangling_path

        detail =
          if dangling == [] do
            "points at #{length(paths)} file(s) shipped beside the parquet, e.g. #{example}. " <>
              "Every artefact a row produced lives in the parquet."
          else
            "points at #{length(dangling)} file(s) the dataset does not contain, " <>
              "e.g. #{hd(dangling)}."
          end

        [%Finding{kind: kind, repo: repo, table: table, column: column, detail: detail}]
    end
  end

  @doc "Features the card declares that no table carries."
  def undelivered_features(repo, features, columns) do
    for {name, dtype} <- features, name not in columns do
      %Finding{
        kind: :undelivered_feature,
        repo: repo,
        table: "(card)",
        column: name,
        detail: "the card declares #{name} as #{dtype} and no table carries that column"
      }
    end
  end

  @doc """
  Checks a published dataset. Downloads each parquet once, reads it, and
  returns every finding with the table and column named.
  """
  def check(repo, opts \\ []) do
    cache = Keyword.get(opts, :cache, Path.join(System.tmp_dir!(), "fbd_payload"))
    File.mkdir_p!(cache)

    with {:ok, files} <- files(repo) do
      features =
        case declared_features(repo) do
          {:ok, f} -> f
          _ -> %{}
        end

      parquets = files |> Enum.filter(&String.ends_with?(&1, ".parquet")) |> Enum.sort()

      {findings, columns} =
        Enum.reduce(parquets, {[], []}, fn table, {acc, cols} ->
          local = Path.join(cache, String.replace(table, "/", "_"))
          fetch(repo, table, local)
          df = DF.from_parquet!(local)
          {acc ++ check_table(repo, table, local, files, features), cols ++ DF.names(df)}
        end)

      no_parquet =
        if parquets == [] do
          [
            %Finding{
              kind: :no_parquet,
              repo: repo,
              table: "(dataset)",
              column: "(none)",
              detail:
                "holds #{MapSet.size(files)} file(s) and no parquet, so there is nothing to " <>
                  "check and nothing carries the payload. A dataset with no table is not a " <>
                  "dataset that passed."
            }
          ]
        else
          []
        end

      {:ok, no_parquet ++ findings ++ undelivered_features(repo, features, Enum.uniq(columns)),
       %{parquets: length(parquets), files: MapSet.size(files)}}
    end
  end

  defp fetch(repo, path, local) do
    unless File.exists?(local) do
      url = "#{@hub}/datasets/#{repo}/resolve/main/#{path}"
      %{status: 200} = Req.get!(url, into: File.stream!(local), receive_timeout: :infinity)
    end

    local
  end
end
