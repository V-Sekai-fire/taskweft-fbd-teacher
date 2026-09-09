defmodule TaskweftFbdTeacher.Runner do
  @moduledoc """
  What a trait's runner must answer. A runner performs a program's method bundle
  and returns the physical quantity the row is scored on, or a refusal that names
  its reason.
  """

  @type job :: map()
  @type result :: {:ok, map()} | {:refused, term()}

  @callback start(keyword()) :: {:ok, pid() | map()} | {:error, term()}
  @callback run(state :: pid() | map(), job) :: result
  @callback provenance(state :: pid() | map()) :: map()
  @callback stop(state :: pid() | map()) :: :ok

  @optional_callbacks start: 1, stop: 1
end
