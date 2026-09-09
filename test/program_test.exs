defmodule TaskweftFbdTeacher.ProgramTest do
  use ExUnit.Case, async: true

  alias TaskweftFbdTeacher.Fbd.Program

  defp lines(list), do: Enum.join(list, "
") <> "
"

  defp write_hello do
    %Program{name: "write_hello", vars: [{"done", "BOOL"}]}
    |> Program.add_block(
      Program.block("b3", "WRITE_FILE", [
        {"PATH", {:string, "out.txt"}},
        {"TEXT", {:string, "hello"}}
      ])
    )
    |> Program.add_block(
      Program.block("b5", "READ_FILE", [
        {"EN", {:ref, "b3", "ENO"}},
        {"PATH", {:string, "out.txt"}}
      ])
    )
    |> Program.write("done", {:ref, "b5", "ENO"})
  end

  test "prints the compiler's own write_hello fixture" do
    assert Program.print(write_hello()) ==
             lines([
               "program write_hello",
               "var done : BOOL",
               "b3 = WRITE_FILE(PATH=\"out.txt\", TEXT=\"hello\")",
               "b5 = READ_FILE(EN=b3.ENO, PATH=\"out.txt\")",
               "done = b5.ENO"
             ])
  end

  test "prints a scan program with declarations, a call and every literal form" do
    p =
      %Program{
        name: "react_planned",
        ins: [{"trigger", "BOOL"}],
        outs: [{"face_from_stick", "BOOL"}, {"style", "INT"}],
        vars: [{"holding0", "BOOL"}]
      }
      |> Program.add_block(Program.block("b2", "R_TRIG", [{"CLK", {:var, "trigger"}}]))
      |> Program.add_block(
        Program.block("b5", "SEL", [
          {"G", {:ref, "b2", "Q"}},
          {"IN0", {:var, "face_from_stick"}},
          {"IN1", {:bool, true}}
        ])
      )
      |> Program.add_block(
        Program.block("b11", "TON", [{"IN", {:var, "holding0"}}, {"PT", {:time_ms, 500}}])
      )
      |> Program.add_block(
        Program.block("b12", "MUL", [{"IN1", {:real, 1.2}}, {"IN2", {:int, 30}}])
      )
      |> Program.add_block(
        Program.call("b13", "Node.get_node", [
          {"TARGET", {:string, "/root/Fixture"}},
          {"path", {:string, "Body"}}
        ])
      )
      |> Program.add_block(
        Program.block("b14", "MUL", [
          {"IN1", {:code, "gain", [5, 2, 7]}},
          {"IN2", {:var, "trigger"}}
        ])
      )
      |> Program.write("face_from_stick", {:ref, "b5", "OUT"})

    assert Program.print(p) ==
             lines([
               "program react_planned",
               "in trigger : BOOL",
               "out face_from_stick : BOOL",
               "out style : INT",
               "var holding0 : BOOL",
               "b2 = R_TRIG(CLK=trigger)",
               "b5 = SEL(G=b2.Q, IN0=face_from_stick, IN1=TRUE)",
               "b11 = TON(IN=holding0, PT=T#500ms)",
               "b12 = MUL(IN1=1.2, IN2=30)",
               "b13 = CALL[Node.get_node](TARGET=\"/root/Fixture\", path=\"Body\")",
               "b14 = MUL(IN1=gain#5.2.7, IN2=trigger)",
               "face_from_stick = b5.OUT"
             ])
  end

  test "time literals print as seconds only on the second" do
    assert Program.value({:time_ms, 2000}) == "T#2s"
    assert Program.value({:time_ms, 500}) == "T#500ms"
    assert Program.value({:real, 2.0}) == "2.0"
    assert Program.value({:bool, false}) == "FALSE"
  end

  test "a string carrying a character the grammar forbids is refused" do
    for bad <- ["it's", "a<b", "x&y", ~s(say "hi")] do
      assert_raise ArgumentError, fn -> Program.value({:string, bad}) end
    end
  end

  test "mutations are struct edits and name what is missing" do
    p = write_hello()

    changed = Program.set_pin(p, "b3", "TEXT", {:string, "goodbye"})
    assert Program.print(changed) =~ ~s(TEXT="goodbye")
    assert Program.print(p) =~ ~s(TEXT="hello")

    dropped = Program.drop_pin(p, "b3", "TEXT")
    refute Program.print(dropped) =~ "TEXT="

    swapped = Program.swap_pins(p, "b3", "PATH", "TEXT")
    assert Program.print(swapped) =~ "b3 = WRITE_FILE(PATH=\"hello\", TEXT=\"out.txt\")"

    assert Program.print(Program.set_kind(p, "b5", "WRITE_FILE")) =~ "b5 = WRITE_FILE("

    assert_raise ArgumentError, ~r/no block b9/, fn ->
      Program.set_pin(p, "b9", "PATH", {:int, 1})
    end

    assert_raise ArgumentError, ~r/has no pin NOPE/, fn ->
      Program.set_pin(p, "b3", "NOPE", {:int, 1})
    end
  end

  test "reports the signatures and kinds a census counts" do
    p =
      write_hello()
      |> Program.add_block(
        Program.call("b7", "Node3D.set_position", [{"TARGET", {:string, "/root/Body"}}])
      )

    assert Program.signatures(p) == ["Node3D.set_position"]
    assert Program.kinds(p) == ["WRITE_FILE", "READ_FILE", "CALL"]
  end
end
