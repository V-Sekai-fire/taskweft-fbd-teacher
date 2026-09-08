# elixir_make spawns MAKE with :spawn_executable, which refuses a .cmd shim.
# Windows desks have `make` on PATH as one; resolve the real executable once.
if System.get_env("MAKE") == nil do
  case System.find_executable("make") do
    nil -> :ok
    path -> System.put_env("MAKE", path)
  end
end

# The ReBAC NIF is a C++ shared object; on Windows it needs the C++ runtime that
# ships beside the compiler that built it. Put that directory on PATH so the
# library loads without the caller remembering, and leave PATH alone elsewhere.
if match?({:win32, _}, :os.type()) do
  from_path =
    case System.find_executable("clang++") do
      nil -> []
      exe -> [Path.dirname(exe)]
    end

  # The same toolchain root the door's mix tasks use, when it is not on PATH yet.
  installed = Path.wildcard(Path.expand("~/llvm-mingw/*/bin"))

  case Enum.find(from_path ++ installed, &File.exists?(Path.join(&1, "libc++.dll"))) do
    nil ->
      :ok

    dir ->
      current = System.get_env("PATH", "")
      unless String.contains?(current, dir), do: System.put_env("PATH", dir <> ";" <> current)
  end
end

defmodule TaskweftFbdTeacher.MixProject do
  use Mix.Project

  def project do
    [
      app: :taskweft_fbd_teacher,
      version: "0.1.0",
      elixir: "~> 1.17",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [extra_applications: [:logger]]
  end

  defp deps do
    [
      {:explorer, "~> 0.12"},
      {:nimble_parsec, "~> 1.4"},
      {:sourceror, "~> 1.12"},
      {:nimble_pool, "~> 1.1"},
      {:jason, "~> 1.4"},
      {:req, "~> 0.5"},
      {:tokenizers, "~> 0.5"},
      {:taskweft_rebac, "~> 0.2.0-dev"},
      {:yaml_elixir, "~> 2.9"}
    ]
  end
end
