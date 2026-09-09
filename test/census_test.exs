defmodule TaskweftFbdTeacher.CensusTest do
  @moduledoc """
  The parser is tested hermetically. The parity test against the Python census needs a
  written stage under `work/`, which is scratch and not committed, so it is tagged and
  reported as excluded rather than silently passing when the stage is absent.
  """
  use ExUnit.Case, async: true

  alias TaskweftFbdTeacher.Census

  describe "block kinds, read by splitting rather than by pattern" do
    test "an assignment names the block it opens" do
      text = """
      program write_file
      var done : BOOL
      b3 = WRITE_FILE(PATH="ember_583.txt", TEXT="islet")
      done = b3.ENO
      """

      assert Census.block_kinds(text) == ["WRITE_FILE"]
    end

    test "a bracketed block counts, and a plain assignment does not" do
      assert Census.block_kinds("a = TON[PT:=T#1s]\nb = c.OUT\n") == ["TON"]
    end

    test "a CALL is counted by its signature, never as CALL" do
      text = "x = CALL[Anny.build](seed)\ny = AND(a, b)\n"
      assert Census.block_kinds(text) == ["AND", "Anny.build"]
    end

    test "a signature without a dot is not a signature" do
      assert Census.block_kinds("x = CALL[nodot](s)\n") == []
    end

    test "an indented assignment is not a block, matching the anchored form" do
      assert Census.block_kinds("  b3 = WRITE_FILE(x)\n") == []
    end

    test "text with no blocks yields none" do
      assert Census.block_kinds("program p\nvar done : BOOL\n") == []
    end
  end

  @stage "work/stage"

  describe "the census over a written stage" do
    @describetag :stage

    setup do
      if File.dir?(@stage), do: :ok, else: {:skip, "no stage at #{@stage}"}
    end

    test "counts agree with the Python census this port replaces" do
      {report, problems} = Census.run([@stage])

      assert problems == []
      assert report["train_rows"] + report["test_rows"] + report["evaluation_rows"] == 5000
      assert report["block_kinds_present"] == map_size(report["block_kinds"])
    end

    test "a planted held-out block kind is refused" do
      assert {:ok, _kind} = Census.self_test([@stage])
    end

    test "a holdout axis no held-out row exercises is reported as empty" do
      {_, problems} = Census.run([@stage], MapSet.new(), MapSet.new(["NOT_A_REAL_BLOCK"]))
      assert Enum.any?(problems, &String.contains?(&1, "the axis is empty"))
    end
  end
end
