defmodule TaskweftFbdTeacher.Runner.CompilerTest do
  use ExUnit.Case, async: true

  alias TaskweftFbdTeacher.Fbd.Program
  alias TaskweftFbdTeacher.Runner.Compiler

  @bin Path.expand(
         "../../taskweft-fbd-compiler/.lake/build/bin/taskweft_fbd_compiler.exe",
         __DIR__
       )
  @sigs Path.expand("../../taskweft-fbd-compiler/sigs", __DIR__)

  defp compiler do
    case Compiler.start(bin: @bin, sigs: @sigs) do
      {:ok, c} -> c
      {:error, why} -> flunk("compiler not startable: #{inspect(why)}")
    end
  end

  test "refuses a path that is not a compiler" do
    assert {:error, {:no_compiler, _}} =
             Compiler.start(bin: Path.join(System.tmp_dir!(), "nope.exe"))
  end

  @tag :compiler
  test "records the compiler's commit sha rather than an unknown" do
    c = compiler()
    p = Compiler.provenance(c)
    assert p.compiler_sha =~ ~r/^[0-9a-f]{40}$/
    assert p.sigs_dir == @sigs
  end

  @tag :compiler
  test "checks a printed program and refuses one the lowering rejects" do
    c = compiler()

    good =
      %Program{name: "write_hello", vars: [{"done", "BOOL"}]}
      |> Program.add_block(
        Program.block("b3", "WRITE_FILE", [
          {"PATH", {:string, "out.txt"}},
          {"TEXT", {:string, "hello"}}
        ])
      )
      |> Program.write("done", {:ref, "b3", "ENO"})

    assert {:ok, %{mode: :check}} = Compiler.run(c, %{mode: :check, source: good})

    bad = Program.drop_pin(good, "b3", "TEXT")

    assert {:refused, %{mode: :check, exit: code, stderr: why}} =
             Compiler.run(c, %{mode: :check, source: bad})

    assert code != 0
    assert why != ""
  end
end
