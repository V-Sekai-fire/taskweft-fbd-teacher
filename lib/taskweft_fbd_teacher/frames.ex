defmodule TaskweftFbdTeacher.Frames do
  @moduledoc """
  Constructed sentence frames: the same diagram under several intents. A template
  names its parameters, a frame is a sentence over those names, and the frame is
  picked by seed and recorded as `frame_id`, so the diagram is unchanged and only
  the words move. Every frame is written by hand.
  """

  @frames %{
    "write" => [
      "write {text} to {path}",
      "put the text {text} into a file called {path}",
      "create {path} containing {text}",
      "save {text} as {path}"
    ],
    "write_then_read" => [
      "write {text} to {path}, then check that {path} exists",
      "create {path} with {text} and confirm the file is there afterwards",
      "after saving {text} into {path}, read {path} back to be sure"
    ],
    "run_print" => [
      "run python and print {n}",
      "use python to print the number {n}",
      "print {n} with a python one-liner"
    ],
    "write_then_count" => [
      "create {k} file(s) named {names} and count the files in the directory",
      "make the files {names} ({k} of them), then report how many files the directory holds",
      "write {names} and count what is in the folder afterwards"
    ],
    "walk_from_stick" => [
      "walk where the left stick points, {gain} times the stick, at most {cap} metres per second",
      "move in the stick's direction with gain {gain}; never faster than {cap} m/s",
      "the left stick drives walking: scale it by {gain} and cap the speed at {cap}"
    ],
    "face_the_stick" => [
      "face the way the left stick points",
      "turn to face the stick direction every frame",
      "keep the facing aligned with the left stick"
    ],
    "tracker_lost_freezes" => [
      "freeze the hair chains once the tracker has been gone for {ms} milliseconds",
      "if the tracker drops out for {ms} ms, stop the chain simulation",
      "when tracking is lost for longer than {ms} milliseconds, hold the chains still"
    ],
    "button_sequence_then_idle" => [
      "when the button is pressed play style {style} for {ms} milliseconds, then idle",
      "on a button press, switch to style {style}, hold it {ms} ms, and go back to idle",
      "a press of the button starts style {style}; after {ms} milliseconds return to idle"
    ],
    "speed_limited_run" => [
      "run at {gain} times the stick, never faster than {cap} metres per second",
      "scale the stick by {gain} for running speed and limit it to {cap} m/s",
      "running speed is the stick times {gain}, clamped at {cap}"
    ]
  }

  def frames, do: @frames

  def for_template(id), do: Map.fetch!(@frames, id)

  @doc "Picks the frame by seed and fills its placeholders, returning `{frame_id, sentence}`."
  def pick(template_id, seed, params) do
    frames = for_template(template_id)
    i = rem(seed, length(frames))
    {i, fill(Enum.at(frames, i), params)}
  end

  defp fill(frame, params) do
    Regex.replace(~r/\{(\w+)\}/, frame, fn _, key ->
      case Map.fetch(params, String.to_atom(key)) do
        {:ok, v} -> to_string(v)
        :error -> raise KeyError, "frame wants #{key}, which the template did not name"
      end
    end)
  end
end
