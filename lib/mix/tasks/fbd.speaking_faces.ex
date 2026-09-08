defmodule Mix.Tasks.Fbd.SpeakingFaces do
  @shortdoc "Converts Speaking_Faces subjects into per-stream zstd parquet"
  @moduledoc """
      mix fbd.speaking_faces subjects --out work/speaking_faces
      mix fbd.speaking_faces convert --subject 24 --out work/speaking_faces
      mix fbd.speaking_faces convert --all --resume --out work/speaking_faces

  Every subject writes a manifest; `--resume` skips subjects that have one and
  counts them. A refused zip stops the run and names the entry.
  """
  use Mix.Task

  alias TaskweftFbdTeacher.SpeakingFaces

  @switches [out: :string, cache: :string, subject: :integer, all: :boolean, resume: :boolean]

  @impl true
  def run(argv) do
    {:ok, _} = Application.ensure_all_started(:req)
    {opts, args, []} = OptionParser.parse(argv, strict: @switches)
    out = Keyword.get(opts, :out, "work/speaking_faces")
    cache = Keyword.get(opts, :cache, Path.join(out, "zips"))

    case args do
      ["subjects"] ->
        subjects(out, cache)

      ["convert"] ->
        convert(opts, out, cache)

      _ ->
        Mix.raise(
          "usage: mix fbd.speaking_faces (subjects | convert) [--subject N | --all] [--resume] [--out DIR]"
        )
    end
  end

  defp subjects(out, cache) do
    subjects = SpeakingFaces.subjects(cache)
    result = SpeakingFaces.write_subjects(subjects, out)
    counts = subjects |> Enum.map(& &1.split) |> Enum.frequencies()

    Mix.shell().info(
      "subjects #{result.subjects}, accessory rows #{result.accessories}, splits #{inspect(counts)}"
    )
  end

  defp convert(opts, out, cache) do
    subjects = SpeakingFaces.subjects(cache)
    by_id = Map.new(subjects, &{&1.sub_id, &1})

    targets =
      cond do
        opts[:all] -> Enum.map(subjects, & &1.sub_id)
        opts[:subject] -> [opts[:subject]]
        true -> Mix.raise("pass --subject N or --all")
      end

    {skipped, todo} =
      Enum.split_with(targets, fn id ->
        opts[:resume] &&
          File.exists?(Path.join([out, "manifest", "sub_#{SpeakingFaces.pad(id)}.json"]))
      end)

    if skipped != [],
      do:
        Mix.shell().info(
          "resume: #{length(skipped)} subjects already converted, skipped by manifest"
        )

    for id <- todo do
      subject = Map.fetch!(by_id, id)

      case SpeakingFaces.convert_subject(id, subject.split, out, cache) do
        {:ok, m} ->
          empties = for {p, z} <- m.zips, z.empty, do: p

          Mix.shell().info(
            "sub_#{SpeakingFaces.pad(id)} #{m.split}: #{m.rows} rows, #{Float.round(m.bytes / 1.0e9, 2)} GB, #{Float.round(m.wall_s, 1)} s#{if empties != [], do: ", empty zips: #{inspect(empties)}", else: ""}"
          )

        {:error, {path, reason}} ->
          Mix.raise("FAIL sub_#{SpeakingFaces.pad(id)} #{path}: #{inspect(reason)}")
      end
    end
  end
end
