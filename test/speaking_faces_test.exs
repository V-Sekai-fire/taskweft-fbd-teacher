defmodule TaskweftFbdTeacher.SpeakingFacesTest do
  use ExUnit.Case, async: true

  alias Explorer.DataFrame, as: DF
  alias TaskweftFbdTeacher.SpeakingFaces

  @png <<137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13>>
  @wav <<"RIFF", 36, 0, 0, 0, "WAVE">>

  test "parses the three entry shapes" do
    assert {:ok, %{kind: :still, sub: 140, trial: 1, pos: 7, frame: 791, stream: 3}} =
             SpeakingFaces.parse("sub_140_io/trial_1/rgb_image_aligned/140_1_1_7_791_3.png")

    assert {:ok, %{kind: :cmd, sub: 24, trial: 2, pos: 1, cmd: 1016, frame: 10, stream: 1}} =
             SpeakingFaces.parse("sub_24_ia/trial_2/thr_image_cmd/24_2_2_1_1016_10_1.png")

    assert {:ok, %{kind: :utterance, sub: 24, trial: 1, pos: 9, cmd: 365, mic: 1}} =
             SpeakingFaces.parse("sub_24_ia/trial_1/mic1_audio_cmd_trim/24_1_2_9_365_1.wav")
  end

  test "refuses names that disagree with their directory or shape" do
    assert {:error, {:stream_dir_disagrees, _}} =
             SpeakingFaces.parse("sub_140_io/trial_1/rgb_image/140_1_1_7_791_3.png")

    assert {:error, {:trial_dir_disagrees, _}} =
             SpeakingFaces.parse("sub_140_io/trial_2/rgb_image/140_1_1_7_791_2.png")

    assert {:error, {:unrecognised_fields, _}} =
             SpeakingFaces.parse("sub_140_io/trial_1/rgb_image/140_1_1_7_2.png")

    assert {:error, {:not_an_integer, _}} =
             SpeakingFaces.parse("sub_140_io/trial_1/rgb_image/140_1_1_x_791_2.png")
  end

  test "a synthetic zip converts to parquet with the entry count, and a bad magic refuses" do
    dir = Path.join(System.tmp_dir!(), "sf_test_#{System.unique_integer([:positive])}")
    File.mkdir_p!(dir)

    good = [
      {~c"sub_7_io/trial_1/rgb_image/7_1_1_1_1_2.png", @png},
      {~c"sub_7_io/trial_1/rgb_image/7_1_1_1_2_2.png", @png},
      {~c"sub_7_io/trial_1/thr_image/7_1_1_1_1_1.png", @png},
      {~c"sub_7_io/trial_2/mic1_audio_cmd_trim/7_2_2_3_100_1.wav", @wav}
    ]

    {:ok, zip} = :zip.create(String.to_charlist(Path.join(dir, "good.zip")), good)
    out = Path.join(dir, "out")
    groups = SpeakingFaces.convert_zip(to_string(zip), 7, "train", out)
    assert is_list(groups)
    counts = Map.new(groups, fn {g, v} -> {g, v.rows} end)
    assert counts == %{{:still, 2, 1} => 2, {:still, 1, 1} => 1, {:audio, 0, 2} => 1}

    visual =
      DF.from_parquet!(Path.join([out, "train", "still", "visual", "sub_007_trial_1.parquet"]))

    assert DF.n_rows(visual) == 2
    assert DF.dtypes(visual)["png"] == :binary
    assert Enum.all?(DF.to_rows(visual), &(&1["png"] == @png))

    bad = [{~c"sub_7_io/trial_1/rgb_image/7_1_1_1_1_2.png", <<"not a png">>}]
    {:ok, zip2} = :zip.create(String.to_charlist(Path.join(dir, "bad.zip")), bad)
    assert {:error, {:not_a_png, _}} = SpeakingFaces.convert_zip(to_string(zip2), 7, "train", out)

    wrong_subject = [{~c"sub_8_io/trial_1/rgb_image/8_1_1_1_1_2.png", @png}]
    {:ok, zip3} = :zip.create(String.to_charlist(Path.join(dir, "wrong.zip")), wrong_subject)

    assert {:error, {:subject_disagrees, _}} =
             SpeakingFaces.convert_zip(to_string(zip3), 7, "train", out)

    File.rm_rf!(dir)
  end

  test "wav magic is required for utterances and png magic for frames" do
    assert :ok = SpeakingFaces.check_magic(%{kind: :utterance}, @wav)
    assert {:error, :not_a_wav} = SpeakingFaces.check_magic(%{kind: :utterance}, @png)
    assert :ok = SpeakingFaces.check_magic(%{kind: :still}, @png)
    assert {:error, :not_a_png} = SpeakingFaces.check_magic(%{kind: :cmd}, @wav)
  end
end
