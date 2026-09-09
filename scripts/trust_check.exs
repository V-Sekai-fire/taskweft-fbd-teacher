alias TaskweftFbdTeacher.Trust

{:ok, list} = Trust.load()
IO.puts("rebac available: #{Trust.available?()}")

for target <- System.argv() do
  IO.puts("#{target}: #{inspect(Trust.check(list, target))}")
end
