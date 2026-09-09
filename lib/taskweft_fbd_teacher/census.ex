defmodule TaskweftFbdTeacher.Census do
  @moduledoc """
  The corpus census and the gate on it. Counts rows per family, template and frame, the
  block kinds each rank1 program uses, the program length histogram, and the two holdout
  axes: a family or a block kind named as held out must appear in no training row.

  Block kinds are read by splitting rather than by pattern, because the operator's ruling
  is to parse where parsing is possible and because `fbd.no_regex` is a gate this module
  has to pass.
  """

  alias Explorer.DataFrame, as: DF
  alias Explorer.Series

  @upper ~c"ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
  @sig ~c"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_."

  @doc "Block kinds in a text-form program, a CALL counted by its signature."
  def block_kinds(text) do
    Enum.reject(assignments(text), &(&1 == "CALL")) ++ call_signatures(text)
  end

  defp assignments(text) do
    text
    |> String.split("\n")
    |> Enum.flat_map(fn line ->
      case String.split(line, " = ", parts: 2) do
        [lhs, rhs] -> if word?(lhs), do: opening_kind(rhs), else: []
        _ -> []
      end
    end)
  end

  # The kind is an upper-case run immediately followed by its argument bracket, which is
  # what separates `b3 = WRITE_FILE(...)` from an assignment of a plain name.
  defp opening_kind(rhs) do
    {kind, rest} = Enum.split_while(String.to_charlist(rhs), &(&1 in @upper))

    if kind != [] and match?([c | _] when c in [?[, ?(], rest),
      do: [List.to_string(kind)],
      else: []
    end

  defp word?(s), do: s != "" and String.to_charlist(s) |> Enum.all?(&(&1 in ~c"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"))

  defp call_signatures(text), do: call_signatures(text, [])

  defp call_signatures(text, acc) do
    case String.split(text, "CALL[", parts: 2) do
      [_] ->
        Enum.reverse(acc)

      [_, rest] ->
        {sig, tail} = Enum.split_while(String.to_charlist(rest), &(&1 in @sig))
        sig = List.to_string(sig)

        acc =
          if match?([?] | _], tail) and String.contains?(sig, "."), do: [sig | acc], else: acc

        call_signatures(List.to_string(tail), acc)
    end
  end

  @doc "rank1 rows of one split, with the program text each names."
  def rows_of(stage, split_dir) do
    family = family_of(stage)
    root = read_table(Path.join(split_dir, "#{family}_root"))
    cands = read_table(Path.join(split_dir, "#{family}_candidates"))

    if root == nil or cands == nil do
      []
    else
      rank1 =
        cands
        |> Enum.filter(&(&1["candidate"] == "rank1"))
        |> Map.new(&{&1["row_key"], &1})

      for r <- root, c = rank1[r["key"]], c != nil do
        text = c["fbd_text"] || c["fbd_xml"] || ""

        %{
          family: family,
          template: r["template_id"],
          frame: r["frame_id"] || 0,
          blocks: block_kinds(text)
        }
      end
    end
  end

  defp family_of(stage) do
    Path.join(stage, "manifest.json")
    |> File.read!()
    |> :json.decode()
    |> Map.get("family", "fbd")
  end

  defp read_table(dir) do
    file =
      cond do
        File.dir?(dir) -> dir |> Path.join("*.parquet") |> Path.wildcard() |> List.first()
        File.regular?(dir) -> dir
        true -> nil
      end

    with path when is_binary(path) <- file, {:ok, df} <- DF.from_parquet(path) do
      names = DF.names(df)
      cols = Map.new(names, &{&1, df |> DF.pull(&1) |> Series.to_list()})
      for i <- 0..(DF.n_rows(df) - 1)//1, do: Map.new(names, &{&1, Enum.at(cols[&1], i)})
    else
      _ -> nil
    end
  end

  @doc """
  The report and the problems. A held-out family or block kind appearing in a training
  row is a problem, and so is a holdout axis that no held-out row exercises, because an
  empty axis reads as a pass.
  """
  def run(stages, holdout_families \\ MapSet.new(), holdout_blocks \\ MapSet.new()) do
    train = Enum.flat_map(stages, &rows_of(&1, Path.join(&1, "data")))
    test = Enum.flat_map(stages, &rows_of(&1, Path.join([&1, "test", "data"])))

    held =
      Enum.flat_map(stages, fn s ->
        Enum.flat_map(["holdout", "evaluation"], &rows_of(s, Path.join([s, &1, "data"])))
      end)

    leaked_family = Enum.any?(train, &MapSet.member?(holdout_families, &1.template))

    leaked_blocks =
      train
      |> Enum.flat_map(& &1.blocks)
      |> Enum.filter(&MapSet.member?(holdout_blocks, &1))
      |> Enum.uniq()
      |> Enum.sort()

    empty_axes =
      holdout_blocks
      |> Enum.sort()
      |> Enum.reject(fn b -> Enum.any?(held, &(b in &1.blocks)) end)

    problems =
      (if leaked_family, do: ["a held-out family leaked into training"], else: []) ++
        Enum.map(leaked_blocks, &"held-out block kind #{&1} leaked into training") ++
        Enum.map(empty_axes, &"held-out block kind #{&1} appears in no holdout row either; the axis is empty")

    report = %{
      "train_rows" => length(train),
      "test_rows" => length(test),
      "evaluation_rows" => length(held),
      "families" => tally(train, & &1.family),
      "templates" => tally(train, & &1.template),
      "frames" => tally(train, &"#{&1.template}##{&1.frame}"),
      "block_kinds" => tally(train, & &1.blocks, :flat),
      "length_histogram" => tally(train, &to_string(length(&1.blocks))),
      "holdout_families" => Enum.sort(holdout_families),
      "holdout_blocks" => Enum.sort(holdout_blocks)
    }

    {Map.put(report, "block_kinds_present", map_size(report["block_kinds"])), problems}
  end

  # A block kind is counted once per row, matching the set the Python census takes.
  defp tally(rows, fun, :flat),
    do: rows |> Enum.flat_map(&(&1 |> fun.() |> Enum.uniq())) |> Enum.frequencies()

  defp tally(rows, fun), do: rows |> Enum.map(fun) |> Enum.frequencies()

  @doc "Plants the most common block kind as held out; the census must refuse it."
  def self_test(stages) do
    {report, _} = run(stages)

    case Enum.max_by(report["block_kinds"], &elem(&1, 1), fn -> nil end) do
      nil ->
        {:error, "no block kinds counted; there is nothing for the control to plant"}

      {kind, _} ->
        {_, problems} = run(stages, MapSet.new(), MapSet.new([kind]))

        if Enum.any?(problems, &String.contains?(&1, "leaked")),
          do: {:ok, kind},
          else: {:error, "planted #{kind} was not refused; the census is decoration"}
    end
  end
end
