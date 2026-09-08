defmodule Mix.Tasks.Fbd.Payload.Check do
  @shortdoc "Refuses a published dataset that does not carry its own payload"
  @moduledoc """
      mix fbd.payload.check chibifire/taskweft-fbd-udon-train
      mix fbd.payload.check --all
      mix fbd.payload.check --self-test

  Three refusals: a column holding a path where the payload should be, media
  bytes the viewer cannot render, and a card promising a column no table
  carries. Every dataset checked is named, so a skip cannot read as a pass.
  """
  use Mix.Task

  alias TaskweftFbdTeacher.{Payload, Trust}

  @switches [all: :boolean, self_test: :boolean, cache: :string]

  @known ~w(
    chibifire/taskweft-fbd-editscore-train
    chibifire/taskweft-fbd-react-train
    chibifire/taskweft-fbd-harness-train
    chibifire/taskweft-fbd-compose-train
    chibifire/taskweft-fbd-plan-train
    chibifire/taskweft-fbd-godot-train
    chibifire/taskweft-fbd-trainer-train
    chibifire/taskweft-fbd-udon-train
    chibifire/anny-dress-on-stage-train
    chibifire/anny-render-corpus-train
    chibifire/anny-render-corpus-generated-train
  )

  @impl true
  def run(argv) do
    checked(argv)
  catch
    :done -> :ok
  end

  defp checked(argv) do
    {:ok, _} = Application.ensure_all_started(:req)
    {opts, args, []} = OptionParser.parse(argv, strict: @switches)

    if opts[:self_test] do
      raise_on(self_test())
      if args == [] and opts[:all] != true, do: throw(:done)
    end

    repos = if opts[:all], do: @known, else: args
    if repos == [], do: Mix.raise("name a dataset, or pass --all")

    {:ok, trust} = Trust.load()

    results =
      for repo <- repos do
        case Trust.check(trust, repo) do
          {:error, why} ->
            Mix.shell().info("#{repo}: #{why}")
            {repo, :untrusted}

          :ok ->
            report(repo, Payload.check(repo, cache: opts[:cache] || default_cache()))
        end
      end

    bad = for {repo, findings} <- results, is_list(findings), findings != [], do: repo
    Mix.shell().info("\nchecked #{length(results)} dataset(s); #{length(bad)} refused")
    if bad != [], do: Mix.raise("REFUSED: #{Enum.join(bad, ", ")}")
  end

  defp default_cache, do: Path.join(System.tmp_dir!(), "fbd_payload")

  defp report(repo, {:error, why}) do
    Mix.shell().info("#{repo}: could not read: #{inspect(why)}")
    {repo, :unreadable}
  end

  defp report(repo, {:ok, [], counts}) do
    Mix.shell().info("  ok   #{repo}  #{counts.parquets} parquet(s), #{counts.files} file(s)")
    {repo, []}
  end

  defp report(repo, {:ok, findings, counts}) do
    Mix.shell().info(
      "  BAD  #{repo}  #{counts.parquets} parquet(s), #{length(findings)} finding(s)"
    )

    for f <- findings do
      Mix.shell().info("       #{f.kind} #{f.table}:#{f.column} -- #{f.detail}")
    end

    {repo, findings}
  end

  defp raise_on(0), do: :ok
  defp raise_on(_), do: Mix.raise("the payload gate is decoration")

  @doc false
  def self_test do
    alias Explorer.DataFrame, as: DF
    alias Explorer.Series

    dir = Path.join(System.tmp_dir!(), "payload_self_test_#{System.unique_integer([:positive])}")
    File.mkdir_p!(dir)
    png = <<137, 80, 78, 71, 13, 10, 26, 10, 0, 0>>
    fails = []

    clean =
      DF.new(
        key: Series.from_list(["a"]),
        fbd_text: Series.from_list(["program p\nvar done : BOOL\n"]),
        image:
          Series.from_list([%{"bytes" => png, "path" => "a.png"}],
            dtype: {:struct, [{"bytes", :binary}, {"path", :string}]}
          )
      )

    clean_path = Path.join(dir, "clean.parquet")
    :ok = DF.to_parquet(clean, clean_path)
    files = MapSet.new(["clean.parquet"])
    features = %{"image" => "image"}

    fails =
      case Payload.check_table("r", "clean.parquet", clean_path, files, features) do
        [] -> fails
        f -> ["a clean table was refused: #{inspect(f)}" | fails]
      end

    dangling =
      DF.new(key: Series.from_list(["a"]), fbd_text: Series.from_list(["rows/t/0/rank1.fbd"]))

    dangling_path = Path.join(dir, "dangling.parquet")
    :ok = DF.to_parquet(dangling, dangling_path)

    fails =
      case Payload.check_table("r", "dangling.parquet", dangling_path, files, %{}) do
        [%{kind: :dangling_path}] -> fails
        f -> ["the planted dangling path was not seen: #{inspect(f)}" | fails]
      end

    beside =
      DF.new(
        key: Series.from_list(["a"]),
        garment_front: Series.from_list(["assets/x/garment-0-front.jpg"])
      )

    beside_path = Path.join(dir, "beside.parquet")
    :ok = DF.to_parquet(beside, beside_path)
    with_asset = MapSet.new(["beside.parquet", "assets/x/garment-0-front.jpg"])

    fails =
      case Payload.check_table("r", "beside.parquet", beside_path, with_asset, %{}) do
        [%{kind: :payload_beside}] -> fails
        f -> ["the planted payload beside the parquet was not seen: #{inspect(f)}" | fails]
      end

    bare = DF.new(key: Series.from_list(["a"]), png: Series.from_list([png], dtype: :binary))
    bare_path = Path.join(dir, "bare.parquet")
    :ok = DF.to_parquet(bare, bare_path)

    fails =
      case Payload.check_table("r", "bare.parquet", bare_path, files, %{}) do
        [%{kind: :bare_media}] -> fails
        f -> ["the planted bare media column was not seen: #{inspect(f)}" | fails]
      end

    fails =
      case Payload.undelivered_features("r", %{"absent" => "image"}, ["key"]) do
        [%{kind: :undelivered_feature}] -> fails
        f -> ["the planted undelivered feature was not seen: #{inspect(f)}" | fails]
      end

    # A dataset with no table cannot be checked, and reporting that as a pass is
    # the defect this gate exists to catch, so it is asserted here too.
    fails =
      case Payload.check("chibifire/anny-render-corpus-generated-train", cache: dir) do
        {:ok, [%{kind: :no_parquet} | _], _} -> fails
        other -> ["a dataset with no parquet was not refused: #{inspect(other)}" | fails]
      end

    File.rm_rf!(dir)
    for f <- Enum.reverse(fails), do: Mix.shell().info("FAIL #{f}")
    Mix.shell().info("#{6 - length(fails)} of 6 controls fired.")
    if fails == [], do: 0, else: 1
  end
end
