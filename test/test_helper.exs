# The ReBAC tests need the native library, which wants the toolchain's C++
# runtime on PATH; the bao test needs a policy this desk does not carry. Both
# are excluded by default and reported as excluded, never as passes.
excluded =
  Enum.reject([rebac: not TaskweftFbdTeacher.Trust.available?(), bao: true], &(!elem(&1, 1)))
  |> Enum.map(&elem(&1, 0))

if excluded != [], do: IO.puts("excluding tagged tests: #{inspect(excluded)}")
ExUnit.start(exclude: excluded)
