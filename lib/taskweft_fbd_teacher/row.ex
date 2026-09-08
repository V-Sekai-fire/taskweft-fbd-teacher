defmodule TaskweftFbdTeacher.Row do
  @moduledoc """
  One intent with its three candidates, the shape every trait shares. `expect`
  is the switch: a function means the template knows the answer, `nil` means
  rank1 is the answer and the other candidates are scored against it.
  """

  @enforce_keys [:template_id, :seed, :intent, :rank1, :rank3, :rank5]
  defstruct [
    :template_id,
    :seed,
    :intent,
    :rank1,
    :rank3,
    :rank5,
    traces: [],
    expect: nil,
    frame_id: 0,
    host: :compiler,
    blocks: []
  ]

  @ranks [rank1: 1, rank3: 3, rank5: 5]

  def ranks, do: @ranks

  def candidate(%__MODULE__{} = row, :rank1), do: row.rank1
  def candidate(%__MODULE__{} = row, :rank3), do: row.rank3
  def candidate(%__MODULE__{} = row, :rank5), do: row.rank5

  @doc "The row key, from anything carrying a template id and a seed: a row or a scored row."
  def key(family, %{template_id: template_id, seed: seed}),
    do: "#{family}/#{template_id}/#{seed}"

  @doc """
  The three controls, asserted on every row before anything is written. Their
  wording is the contract the Python writer set and the corpora were built
  under, so it is kept verbatim.
  """
  def assert_controls(key, scores) do
    %{"rank1" => r1, "rank3" => r3, "rank5" => r5} = scores

    cond do
      not (r1["compiles"] and r1["runs"] and r1["effect_matches"]) ->
        {:error, "identity control failed on #{key}: rank1 #{inspect(r1)}"}

      not r3["compiles"] or r3["effect_matches"] ->
        {:error,
         "effect control failed on #{key}: rank3 must compile and miss the effect, got #{inspect(r3)}"}

      r5["compiles"] ->
        {:error, "negative control failed on #{key}: rank5 compiled: #{inspect(r5)}"}

      true ->
        :ok
    end
  end
end
