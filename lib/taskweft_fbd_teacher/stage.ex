defmodule TaskweftFbdTeacher.Stage do
  @moduledoc """
  The four tables of a stage, written as zstd parquet under the split
  directories the dataset viewer reads. Column names and order match the
  corpora already published, so a reader written against those still works.
  A null in any column is refused: the workspace's normal form has no nulls.
  """

  alias Explorer.DataFrame, as: DF
  alias TaskweftFbdTeacher.Row

  @splits [train: "data", test: "test/data", evaluation: "evaluation/data"]

  def splits, do: @splits

  @doc """
  Splits scored rows the way the published corpora are split: held-out
  templates and block kinds to evaluation first, then every tenth seed to
  test, the rest to train.
  """
  def split(rows, holdout_templates, holdout_blocks) do
    templates = MapSet.new(holdout_templates)
    blocks = MapSet.new(holdout_blocks)

    {evaluation, rest} =
      Enum.split_with(rows, fn r ->
        MapSet.member?(templates, r.template_id) or
          Enum.any?(r.blocks, &MapSet.member?(blocks, &1))
      end)

    {test, train} = Enum.split_with(rest, &(rem(&1.seed, 10) == 0))
    %{train: train, test: test, evaluation: evaluation}
  end

  @doc "The root table: one row per intent."
  def root_rows(family, stub, rows) do
    Enum.map(rows, fn r ->
      %{
        "key" => Row.key(family, r),
        "task_type" => stub.task_type,
        "dimension" => stub.dimension,
        "input_column" => stub.input_column,
        "input_asset_kind" => stub.input_asset_kind,
        "intent" => r.intent,
        "template_id" => r.template_id,
        "seed" => r.seed,
        "frame_id" => r.frame_id,
        "blocks" => Enum.join(Enum.sort(r.blocks), ","),
        "provenance" => "constructed:template"
      }
    end)
  end

  def candidate_rows(family, rows) do
    Enum.flat_map(rows, fn r ->
      Enum.map(r.candidates, &Map.put(&1, "row_key", Row.key(family, r)))
    end)
  end

  def score_rows(family, rows) do
    Enum.flat_map(rows, fn r ->
      Enum.map(r.scores, &Map.put(&1, "row_key", Row.key(family, r)))
    end)
  end

  @doc "The joined view: the default config the viewer opens."
  def joined_rows(family, rows) do
    Enum.map(rows, fn r ->
      by_candidate = Map.new(r.scores, &{&1["candidate"], &1})

      %{
        "key" => Row.key(family, r),
        "intent" => r.intent,
        "template_id" => r.template_id,
        "seed" => r.seed,
        "candidates" =>
          Enum.map(r.candidates, fn c ->
            Map.put(c, "scores", Map.fetch!(by_candidate, c["candidate"]))
          end)
      }
    end)
  end

  def tables(family, stub, rows) do
    %{
      "#{family}_root" => root_rows(family, stub, rows),
      "#{family}_candidates" => candidate_rows(family, rows),
      "#{family}_scores" => score_rows(family, rows),
      family => joined_rows(family, rows)
    }
  end

  @doc """
  Writes one split's four tables and returns their row counts. Refuses before
  writing if any column carries a null.
  """
  def write(out, split, family, stub, rows) do
    dir = Path.join(out, Keyword.fetch!(@splits, split))

    Enum.reduce_while(tables(family, stub, rows), {:ok, %{}}, fn {name, table}, {:ok, counts} ->
      case write_table(dir, name, split, table) do
        {:ok, n} -> {:cont, {:ok, Map.put(counts, name, n)}}
        {:error, why} -> {:halt, {:error, why}}
      end
    end)
  end

  defp write_table(_dir, _name, _split, []), do: {:ok, 0}

  defp write_table(dir, name, split, table) do
    df = DF.new(table)

    case nulls(df) do
      [] ->
        path = Path.join([dir, name, "#{split}-00000-of-00001.parquet"])
        File.mkdir_p!(Path.dirname(path))
        :ok = DF.to_parquet(df, path, compression: {:zstd, 3})
        {:ok, DF.n_rows(df)}

      [{col, n} | _] ->
        {:error, "FAIL: #{name}.#{col} carries #{n} null(s); ETNF forbids them"}
    end
  end

  defp nulls(df) do
    for col <- DF.names(df),
        n = df |> DF.pull(col) |> Explorer.Series.nil_count(),
        n > 0,
        do: {col, n}
  end
end
