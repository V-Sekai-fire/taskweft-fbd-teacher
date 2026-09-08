defmodule TaskweftFbdTeacher.Family do
  @moduledoc """
  A family exercises one trait: a set of templates, a runner host, and the
  number of distinct programs each template can produce. `space/1` is what the
  writer allocates against, so a family cannot be asked for more rows than it
  has distinct diagrams.
  """

  alias TaskweftFbdTeacher.Row

  @callback trait() :: atom()
  @callback stub() :: map()
  @callback templates() :: [String.t()]
  @callback space(String.t()) :: pos_integer()
  @callback row(String.t(), non_neg_integer()) :: Row.t()
  @callback host() :: atom()

  @doc """
  Allocates `rows` seeds across templates as `min(space, quota)`, giving the
  remainder to templates that still have room. Refuses a family whose total
  space is below what was asked for, rather than repeating diagrams.
  """
  def allocate(templates, spaces, rows) when rows > 0 do
    total = templates |> Enum.map(&Map.fetch!(spaces, &1)) |> Enum.sum()

    if total < rows do
      {:error, {:space_below_rows, total, rows}}
    else
      {:ok, distribute(templates, spaces, rows)}
    end
  end

  defp distribute(templates, spaces, rows) do
    n = length(templates)
    quota = div(rows, n)

    counts =
      Map.new(templates, fn t -> {t, min(Map.fetch!(spaces, t), quota)} end)

    fill(templates, spaces, counts, rows - elem_sum(counts))
  end

  defp elem_sum(counts), do: counts |> Map.values() |> Enum.sum()

  defp fill(_templates, _spaces, counts, 0), do: counts

  defp fill(templates, spaces, counts, remainder) do
    room = Enum.filter(templates, fn t -> Map.fetch!(counts, t) < Map.fetch!(spaces, t) end)

    if room == [] do
      counts
    else
      {counts, left} =
        Enum.reduce(room, {counts, remainder}, fn
          _t, {acc, 0} -> {acc, 0}
          t, {acc, left} -> {Map.update!(acc, t, &(&1 + 1)), left - 1}
        end)

      fill(templates, spaces, counts, left)
    end
  end

  @doc "Seeds are global and consecutive, so a row's seed names it across a whole stage."
  def jobs(counts, templates) do
    {jobs, _} =
      Enum.reduce(templates, {[], 0}, fn t, {acc, next} ->
        n = Map.fetch!(counts, t)
        {acc ++ Enum.map(next..(next + n - 1)//1, &{t, &1}), next + n}
      end)

    jobs
  end
end
