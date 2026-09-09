defmodule Mix.Tasks.Fbd.Census do
  @shortdoc "Census a stage and gate its holdout axes"

  @moduledoc """
      mix fbd.census <stage>... [--holdout-families a,b] [--holdout-blocks TOF,RS]
      mix fbd.census <stage>... --self-test

  Prints the report as JSON and exits 1 naming every problem. `--self-test` plants the
  most common block kind as held out, which the census must refuse.
  """

  use Mix.Task

  alias TaskweftFbdTeacher.Census

  @impl Mix.Task
  def run(argv) do
    {opts, stages, _} =
      OptionParser.parse(argv,
        strict: [holdout_families: :string, holdout_blocks: :string, self_test: :boolean]
      )

    if stages == [], do: Mix.raise("usage: mix fbd.census <stage>... [--self-test]")

    if opts[:self_test] do
      case Census.self_test(stages) do
        {:ok, kind} ->
          IO.puts("  ok   planted held-out block #{kind} refused")
          System.halt(0)

        {:error, why} ->
          IO.puts("  FAIL #{why}")
          System.halt(1)
      end
    end

    {report, problems} = Census.run(stages, set(opts[:holdout_families]), set(opts[:holdout_blocks]))
    IO.puts(:json.encode(report))
    Enum.each(problems, &IO.puts("FAIL #{&1}"))
    System.halt(if problems == [], do: 0, else: 1)
  end

  defp set(nil), do: MapSet.new()
  defp set(s), do: s |> String.split(",", trim: true) |> MapSet.new()
end
