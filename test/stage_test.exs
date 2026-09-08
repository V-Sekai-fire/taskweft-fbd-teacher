defmodule TaskweftFbdTeacher.StageTest do
  use ExUnit.Case, async: true

  alias Explorer.DataFrame, as: DF
  alias TaskweftFbdTeacher.{Family, Row, Stage}

  @stub %{
    task_type: "intent_to_fbd",
    dimension: "instruction_following",
    input_column: "input_intent",
    input_asset_kind: "text"
  }

  defp scored(template, seed, blocks) do
    candidates =
      for {name, rank} <- Row.ranks() do
        %{
          "candidate" => to_string(name),
          "rank" => rank,
          "fbd_text" => "rows/#{template}/#{seed}/#{name}.fbd",
          "fbd_sha" => String.duplicate("b", 64),
          "traces" => 3,
          "provenance" => "constructed:fbd:#{template}:seed:#{seed}"
        }
      end

    scores =
      for {name, rank} <- Row.ranks() do
        %{
          "candidate" => to_string(name),
          "parses" => true,
          "compiles" => rank != 5,
          "runs" => rank == 1,
          "effect_matches" => rank == 1,
          "steps" => 4,
          "wall_ms" => 12,
          "refusal" => ""
        }
      end

    %{
      template_id: template,
      seed: seed,
      intent: "write #{seed}",
      frame_id: rem(seed, 3),
      blocks: blocks,
      candidates: candidates,
      scores: scores
    }
  end

  test "splits by holdout template, holdout block, then every tenth seed" do
    rows = [
      scored("a", 0, ["AND"]),
      scored("a", 1, ["AND"]),
      scored("b", 10, ["OR"]),
      scored("held", 2, ["AND"]),
      scored("a", 3, ["MOD"])
    ]

    %{train: train, test: test, evaluation: evaluation} = Stage.split(rows, ["held"], ["MOD"])
    assert Enum.map(evaluation, & &1.seed) == [2, 3]
    assert Enum.map(test, & &1.seed) == [0, 10]
    assert Enum.map(train, & &1.seed) == [1]
  end

  test "writes the four tables with the published column names and reads them back" do
    dir = Path.join(System.tmp_dir!(), "stage_test_#{System.unique_integer([:positive])}")
    rows = [scored("a", 0, ["AND", "OR"]), scored("a", 1, ["AND"])]

    assert {:ok, counts} = Stage.write(dir, :train, "fbd", @stub, rows)
    assert counts == %{"fbd" => 2, "fbd_root" => 2, "fbd_candidates" => 6, "fbd_scores" => 6}

    root = DF.from_parquet!(Path.join([dir, "data", "fbd_root", "train-00000-of-00001.parquet"]))

    assert Enum.sort(DF.names(root)) ==
             Enum.sort(~w(key task_type dimension input_column input_asset_kind intent
                          template_id seed frame_id blocks provenance))

    assert DF.to_rows(root) |> hd() |> Map.get("key") == "fbd/a/0"
    assert DF.to_rows(root) |> hd() |> Map.get("blocks") == "AND,OR"

    joined = DF.from_parquet!(Path.join([dir, "data", "fbd", "train-00000-of-00001.parquet"]))
    [first | _] = DF.to_rows(joined)
    assert length(first["candidates"]) == 3
    assert hd(first["candidates"])["scores"]["effect_matches"] == true

    File.rm_rf!(dir)
  end

  test "a null in any column is refused before the parquet is written" do
    dir = Path.join(System.tmp_dir!(), "stage_null_#{System.unique_integer([:positive])}")
    [row] = [scored("a", 0, ["AND"])]
    holed = %{row | candidates: Enum.map(row.candidates, &Map.put(&1, "fbd_sha", nil))}

    assert {:error, why} = Stage.write(dir, :train, "fbd", @stub, [holed])
    assert why =~ "fbd_candidates.fbd_sha carries 3 null(s)"
    File.rm_rf!(dir)
  end

  test "allocates min(space, quota) and refuses a family with too little space" do
    spaces = %{"a" => 100, "b" => 3, "c" => 100}
    assert {:ok, counts} = Family.allocate(~w(a b c), spaces, 30)
    assert counts["b"] == 3
    assert Enum.sum(Map.values(counts)) == 30
    assert counts["a"] + counts["c"] == 27

    assert {:error, {:space_below_rows, 6, 30}} =
             Family.allocate(~w(a b), %{"a" => 3, "b" => 3}, 30)
  end

  test "seeds are consecutive across templates in template order" do
    counts = %{"a" => 2, "b" => 3}
    assert Family.jobs(counts, ~w(a b)) == [{"a", 0}, {"a", 1}, {"b", 2}, {"b", 3}, {"b", 4}]
  end
end
