defmodule TaskweftFbdTeacher.Trust do
  @moduledoc """
  The trusted data sources, as a ReBAC graph. Every fetch of a corpus input and
  every publish asks this module first. `trust.exs` is read as an AST and
  pattern-matched, never evaluated, so a source list cannot run code.

  OpenBao KV `relationships/` is authoritative and `trust.exs` is derived from
  it. This desk's certificate token has no read on that path, so `from_bao/0`
  reports the refusal rather than guessing, and the pair stays a named
  known-failing check until the policy grants the read.
  """

  alias Taskweft.ReBAC

  @default_path "trust.exs"

  @doc "Reads the derived list without evaluating it."
  def load(path \\ @default_path) do
    with {:ok, text} <- File.read(path),
         {:ok, ast} <- Code.string_to_quoted(text) do
      parse(ast)
    else
      {:error, :enoent} -> {:error, {:no_trust_file, path}}
      {:error, why} -> {:error, {:unreadable, why}}
    end
  end

  defp parse({:%{}, _, pairs}) do
    fields = Map.new(pairs)

    with {:ok, subject} <- string(fields, :subject),
         {:ok, verb} <- string(fields, :verb),
         {:ok, objects} <- strings(fields, :objects) do
      {:ok, %{subject: subject, verb: verb, objects: objects}}
    end
  end

  defp parse(_), do: {:error, :not_a_map_literal}

  defp string(fields, key) do
    case Map.fetch(fields, key) do
      {:ok, v} when is_binary(v) -> {:ok, v}
      {:ok, _} -> {:error, {:not_a_string, key}}
      :error -> {:error, {:missing, key}}
    end
  end

  defp strings(fields, key) do
    case Map.fetch(fields, key) do
      {:ok, list} when is_list(list) ->
        if Enum.all?(list, &is_binary/1),
          do: {:ok, list},
          else: {:error, {:not_all_strings, key}}

      {:ok, _} ->
        {:error, {:not_a_list, key}}

      :error ->
        {:error, {:missing, key}}
    end
  end

  @doc """
  Whether the ReBAC library's native part loaded. On Windows its shared object
  wants the toolchain's C++ runtime, so a desk without that on its PATH gets a
  named refusal here rather than an undefined function three frames down.
  """
  def available? do
    ReBAC.add_edge(ReBAC.new_graph(), "probe", "probe", "probe")
    true
  rescue
    UndefinedFunctionError -> false
  end

  @unavailable {:error,
                "REFUSED: the ReBAC library did not load; put the toolchain's runtime on PATH"}

  def unavailable, do: @unavailable

  @doc "Folds the tuples into a ReBAC graph."
  def graph(%{subject: subject, verb: verb, objects: objects}) do
    Enum.reduce(objects, ReBAC.new_graph(), fn object, g ->
      ReBAC.add_edge(g, subject, object, verb)
    end)
  end

  @doc """
  Whether the subject trusts this source. A hub repository is trusted when the
  owner is, so `chibifire/anything` passes under `huggingface.co/chibifire`.

  The answer is computed here rather than delegated. One subject, one verb and
  a flat set of objects is a membership test, and the ReBAC library earns its
  place where relations compose. It stays as the **cross-check**:
  `agrees_with_rebac?/2` asserts the two give the same answer wherever the
  library loads, which is a stronger statement than either alone and does not
  make a Windows library search path a condition of publishing.
  """
  def trusted?(list, source) do
    objects = MapSet.new(list.objects)
    Enum.any?(candidates(source), &MapSet.member?(objects, &1))
  end

  @doc "Whether the ReBAC library agrees, where it loads. `:unavailable` when it does not."
  def agrees_with_rebac?(list, source) do
    if available?() do
      g = graph(list)

      rebac =
        Enum.any?(candidates(source), fn candidate ->
          ReBAC.check_rel(g, list.subject, list.verb, candidate) == true
        end)

      rebac == trusted?(list, source)
    else
      :unavailable
    end
  end

  defp candidates(source) do
    trimmed = String.trim_trailing(source, "/")

    owner =
      case String.split(trimmed, "/") do
        [owner, _repo] -> ["huggingface.co/" <> owner, owner]
        _ -> []
      end

    [trimmed | owner]
  end

  @doc "Refuses with the source named, so a caller cannot mistake a refusal for a pass."
  def check(list, source) do
    if trusted?(list, source),
      do: :ok,
      else: {:error, "REFUSED: #{source} is not a trusted data source"}
  end

  @doc """
  The authoritative tuples from OpenBao. Returns `{:error, {:blocked, reason}}`
  where the policy does not grant the read, which is the state on this desk.
  """
  def from_bao(bao \\ Path.expand("~/bin/bao.exe")) do
    env = [
      {"BAO_ADDR", "https://100.124.200.34:8200"},
      {"BAO_TLS_SERVER_NAME", "weftspun-bao.internal"},
      {"BAO_CACERT", Path.expand("~/.magi/ca-bundle.pem")},
      {"BAO_CLIENT_CERT", Path.expand("~/.magi/v3-leaf-int.pem")},
      {"BAO_CLIENT_KEY", Path.expand("~/.magi/bao-client-v3.key")}
    ]

    with {token, 0} <-
           System.cmd(bao, ["login", "-method=cert", "-no-store", "-field=token"], env: env),
         token = token |> String.split("\n") |> List.last() |> String.trim(),
         {out, 0} <-
           System.cmd(bao, ["kv", "list", "-format=json", "relationships/"],
             env: [{"BAO_TOKEN", token} | env],
             stderr_to_stdout: true
           ) do
      {:ok, Jason.decode!(out)}
    else
      {out, code} -> {:error, {:blocked, code, String.trim(out) |> String.slice(0, 400)}}
    end
  end
end
