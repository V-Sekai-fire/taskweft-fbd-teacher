defmodule TaskweftFbdTeacher.Gd.LiftTest do
  @moduledoc """
  The parity gate for the lift. `test/fixtures/gd_lift_python_parity.json` holds what
  `tools/gd_lift.py` returned for every method of `gd_lift_cases.gd`, which covers the
  forms the lift carries and one method per refusal reason.
  """
  use ExUnit.Case, async: true

  alias TaskweftFbdTeacher.Gd.Lift

  @cases "test/fixtures/gd_lift_cases.gd" |> File.read!()
  @expected "test/fixtures/gd_lift_python_parity.json" |> File.read!() |> :json.decode()

  defp run, do: Lift.lift_all(@cases)

  test "every method lifts or refuses exactly as the Python did" do
    {lifted, refused} = run()
    assert lifted == @expected["lifted"]
    assert refused == @expected["refused"]
  end

  test "the fixture exercises both halves" do
    assert map_size(@expected["lifted"]) == 20
    assert map_size(@expected["refused"]) == 29
  end

  test "a planted change to a lifted program is caught by the same comparison" do
    {lifted, _} = run()
    planted = Map.update!(lifted, "add_two", &(&1 <> "\n"))
    refute planted == @expected["lifted"]
  end

  test "a SEL takes its number before its operands, and is emitted below them" do
    {lifted, _} = run()
    text = lifted["ternary_form"]
    assert text =~ "b2 = GT(IN1=a, IN2=b)"
    assert text =~ "b1 = SEL(G=b2.OUT, IN0=b, IN1=a)"
    # numbered first, written second: the operand's block has to sit above the reader
    lines = String.split(text, "\n")
    assert Enum.find_index(lines, &String.starts_with?(&1, "b2 =")) <
             Enum.find_index(lines, &String.starts_with?(&1, "b1 ="))
  end

  test "a parameter returned unchanged goes through MOVE" do
    {lifted, _} = run()
    assert lifted["passthrough"] =~ "MOVE(IN=a)"
  end

  test "a refusal names its reason" do
    {_, refused} = run()
    assert refused["for_loop"] == "for loop"
    assert refused["abs_call"] == "call: abs (no ABS block)"
    assert refused["udon_hook"] == "runtime hook"
  end
end
