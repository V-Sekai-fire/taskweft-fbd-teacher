defmodule TaskweftFbdTeacher.Runner.Compiler do
  @moduledoc """
  The Lean compiler as a runner. Every job passes `--sigs` explicitly so the
  table set is in the command rather than the environment, and a compiler whose
  commit sha cannot be read is a refusal, not an unknown recorded in a manifest.
  """

  @behaviour TaskweftFbdTeacher.Runner

  alias TaskweftFbdTeacher.Fbd.Program

  defstruct [:bin, :sigs, :sha, sigs_mode: :env, timeout: 120_000]

  @impl true
  def start(opts) do
    bin = Keyword.fetch!(opts, :bin) |> Path.expand()

    cond do
      not File.regular?(bin) ->
        {:error, {:no_compiler, bin}}

      true ->
        case sha(bin) do
          {:ok, sha} ->
            {:ok,
             %__MODULE__{
               bin: bin,
               sigs: opts |> Keyword.get(:sigs) |> maybe_expand(),
               sigs_mode: Keyword.get(opts, :sigs_mode, :env),
               sha: sha,
               timeout: Keyword.get(opts, :timeout, 120_000)
             }}

          {:error, why} ->
            {:error, {:compiler_sha_unknown, why}}
        end
    end
  end

  defp maybe_expand(nil), do: nil
  defp maybe_expand(dir), do: Path.expand(dir)

  defp sha(bin) do
    repo = bin |> Path.dirname() |> find_repo()

    cond do
      repo == nil ->
        {:error, {:not_in_a_repository, bin}}

      true ->
        case System.cmd("git", ["-C", repo, "rev-parse", "HEAD"], stderr_to_stdout: true) do
          {out, 0} -> {:ok, String.trim(out)}
          {out, code} -> {:error, {:git_failed, code, String.trim(out)}}
        end
    end
  end

  defp find_repo("/"), do: nil
  defp find_repo("."), do: nil

  defp find_repo(dir) do
    parent = Path.dirname(dir)

    cond do
      File.dir?(Path.join(dir, ".git")) -> dir
      parent == dir -> nil
      true -> find_repo(parent)
    end
  end

  @impl true
  def provenance(%__MODULE__{} = c),
    do: %{compiler_path: c.bin, compiler_sha: c.sha, sigs_dir: c.sigs, sigs_mode: c.sigs_mode}

  @impl true
  def stop(%__MODULE__{}), do: :ok

  @impl true
  def run(%__MODULE__{} = c, %{mode: mode, source: %Program{} = p} = job) do
    dir = scratch()
    file = Path.join(dir, "#{p.name}.fbd")
    File.write!(file, Program.print(p))

    try do
      run(c, Map.merge(job, %{source: file}))
    after
      File.rm_rf!(dir)
    end
    |> tag(mode)
  end

  def run(%__MODULE__{} = c, %{mode: mode, source: file} = job) when is_binary(file) do
    args = [to_string(mode), file] ++ sigs_flag(c) ++ Map.get(job, :args, [])

    case cmd(c, args) do
      {out, 0} -> {:ok, %{mode: mode, stdout: out, json: decode(out)}}
      {out, code} -> {:refused, %{mode: mode, exit: code, stderr: String.trim(out)}}
    end
  end

  defp tag({:ok, m}, mode), do: {:ok, Map.put(m, :mode, mode)}
  defp tag(other, _mode), do: other

  defp sigs_flag(%__MODULE__{sigs: nil}), do: []
  defp sigs_flag(%__MODULE__{sigs_mode: :flag, sigs: dir}), do: ["--sigs", dir]
  defp sigs_flag(%__MODULE__{sigs_mode: :env}), do: []

  defp sigs_env(%__MODULE__{sigs_mode: :env, sigs: dir}) when is_binary(dir),
    do: [env: [{"TASKWEFT_SIGS_DIR", dir}]]

  defp sigs_env(%__MODULE__{}), do: []

  defp cmd(%__MODULE__{} = c, args) do
    opts = [stderr_to_stdout: true] ++ sigs_env(c)
    task = Task.async(fn -> System.cmd(c.bin, args, opts) end)

    case Task.yield(task, c.timeout) || Task.shutdown(task, :brutal_kill) do
      {:ok, result} -> result
      nil -> {"timed out after #{c.timeout} ms", 124}
    end
  end

  defp decode(out) do
    case Jason.decode(String.trim(out)) do
      {:ok, json} -> json
      {:error, _} -> nil
    end
  end

  defp scratch do
    dir = Path.join(System.tmp_dir!(), "fbd_#{System.unique_integer([:positive, :monotonic])}")
    File.mkdir_p!(dir)
    dir
  end
end
