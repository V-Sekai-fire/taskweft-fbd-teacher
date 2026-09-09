defmodule TaskweftFbdTeacher.FramesParityTest do
  @moduledoc """
  The parity gate for the first ported family. `test/fixtures/frames_python_parity.json`
  holds what `tools/frames.py` returned for every template at seeds 0..99, enumerated
  rather than sampled because the population is fixed and small. The Python file cannot
  be deleted yet, since `fbd_templates.py` and `react_templates.py` still import it, so
  this fixture is what keeps the two answers pinned together until they can be.
  """
  use ExUnit.Case, async: true

  alias TaskweftFbdTeacher.Frames

  @cases "test/fixtures/frames_python_parity.json"
         |> File.read!()
         |> :json.decode()

  defp params(c), do: Map.new(c["p"], fn {k, v} -> {String.to_atom(k), v} end)

  # The one comparison both the gate and its control run, so the control exercises the
  # gate rather than a restatement of it.
  defp differing(cases) do
    for c <- cases,
        {i, s} = Frames.pick(c["t"], c["seed"], params(c)),
        i != c["i"] or s != c["s"],
        do: {c["t"], c["seed"]}
  end

  test "every template and seed agrees with what the Python returned" do
    assert differing(@cases) == []
    assert length(@cases) == 900
  end

  test "a planted difference is reported, in the sentence and in the frame index alike" do
    [a, b | _] = @cases
    planted = [%{a | "s" => a["s"] <> " and then"}, %{b | "i" => b["i"] + 1}]

    assert length(differing(planted)) == 2,
           "the comparison passed input it should have refused"
  end

  test "a frame whose placeholder the template did not name is refused, not filled blank" do
    assert_raise KeyError, fn -> Frames.pick("write", 0, %{text: "x"}) end
  end
end
