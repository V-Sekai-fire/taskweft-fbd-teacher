defmodule TaskweftFbdTeacher.TrustTest do
  use ExUnit.Case, async: true

  alias TaskweftFbdTeacher.Trust

  @list %{
    subject: "magi-16739d",
    verb: "trusts",
    objects: [
      "huggingface.co/chibifire",
      "v-sekai-fabric/weftspun-keypoint",
      "chibifire/starforged-std-3001-appendix-e"
    ]
  }

  test "reads the checked-in list as an AST" do
    assert {:ok, list} = Trust.load()
    assert list.subject == "magi-16739d"
    assert list.verb == "trusts"
    assert "huggingface.co/chibifire" in list.objects
  end

  test "the answer does not depend on the native library loading" do
    assert Trust.check(@list, "chibifire/x") == :ok
    assert {:error, _} = Trust.check(@list, "someone/else")
  end

  @tag :rebac
  test "the ReBAC library agrees wherever it loads" do
    for source <- ["chibifire/x", "someone/else", "v-sekai-fabric/weftspun-keypoint"] do
      assert Trust.agrees_with_rebac?(@list, source) in [true, :unavailable]
    end
  end

  @tag :rebac
  test "a hub repository is trusted through its owner" do
    assert Trust.trusted?(@list, "chibifire/taskweft-fbd-udon-train")
    assert Trust.trusted?(@list, "chibifire/starforged-std-3001-appendix-e")
    assert Trust.trusted?(@list, "v-sekai-fabric/weftspun-keypoint")
  end

  @tag :rebac
  test "an untrusted hub, an untrusted owner and a planted model are each refused" do
    for source <- ["google/gemma-4", "issai/Speaking_Faces", "someone/else"] do
      refute Trust.trusted?(@list, source)
      assert {:error, why} = Trust.check(@list, source)
      assert why =~ source
    end
  end

  @tag :rebac
  test "a list under another verb grants nothing" do
    other = %{@list | verb: "reads"}
    graph = Trust.graph(other)
    refute Taskweft.ReBAC.check_rel(graph, "magi-16739d", "trusts", "huggingface.co/chibifire")
  end

  test "a malformed list is refused by shape, not evaluated" do
    dir = Path.join(System.tmp_dir!(), "trust_#{System.unique_integer([:positive])}")
    File.mkdir_p!(dir)

    bad = Path.join(dir, "bad.exs")
    File.write!(bad, ~s(%{subject: "x", verb: "trusts", objects: "not a list"}))
    assert {:error, {:not_a_list, :objects}} = Trust.load(bad)

    File.write!(bad, ~s(%{subject: "x", objects: []}))
    assert {:error, {:missing, :verb}} = Trust.load(bad)

    File.write!(bad, "File.rm_rf!(\"/\")")
    assert {:error, :not_a_map_literal} = Trust.load(bad)

    assert {:error, {:no_trust_file, _}} = Trust.load(Path.join(dir, "absent.exs"))
    File.rm_rf!(dir)
  end

  @tag :bao
  test "the authoritative read reports its refusal rather than guessing" do
    case Trust.from_bao() do
      {:ok, keys} -> assert is_list(keys) or is_map(keys)
      {:error, {:blocked, code, why}} -> assert code != 0 and why != ""
    end
  end
end
