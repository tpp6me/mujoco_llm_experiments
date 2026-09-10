#!/bin/zsh
set -euo pipefail

repo_root=${0:A:h:h}
output_dir="$repo_root/runtime/conveyor/story"
font_bold='/System/Library/Fonts/Supplemental/Arial Bold.ttf'
font_regular='/System/Library/Fonts/Supplemental/Arial.ttf'

mkdir -p "$output_dir"

sources=(
  "$repo_root/runtime/conveyor/phase1/conveyor_transport.mp4"
  "$repo_root/runtime/conveyor/phase2/pushing.mp4"
  "$repo_root/runtime/conveyor/phase3/codex_blue_sorting.mp4"
  "$repo_root/runtime/conveyor/phase4/codex_continuous_success.mp4"
  "$repo_root/runtime/conveyor/phase5/codex_camera_success.mp4"
  "$repo_root/runtime/conveyor/phase6/codex_multi_color.mp4"
)

for source_file in "${sources[@]}"; do
  [[ -f "$source_file" ]] || { print -u2 "Missing source: $source_file"; exit 1; }
done

ffmpeg -y -v warning \
  -f lavfi -i 'color=c=0x07111f:s=1280x720:r=30:d=4' \
  -i "${sources[1]}" -i "${sources[2]}" -i "${sources[3]}" \
  -i "${sources[4]}" -i "${sources[5]}" -i "${sources[6]}" \
  -f lavfi -i 'color=c=0x07111f:s=1280x720:r=30:d=5' \
  -filter_complex "
    [0:v]drawtext=fontfile='$font_bold':text='FROM SIMULATION TO LLM ROBOTICS':fontcolor=white:fontsize=46:x=(w-text_w)/2:y=275,
         drawtext=fontfile='$font_regular':text='Six phases with a MuJoCo SO-101 arm':fontcolor=0x58d6ff:fontsize=30:x=(w-text_w)/2:y=350[intro];
    [1:v]trim=start=0:end=24,setpts=(PTS-STARTPTS)/1.5,fps=30,scale=960:720,pad=1280:720:160:0:color=0x07111f,
         drawbox=x=0:y=625:w=1280:h=95:color=0x07111f@0.94:t=fill,
         drawtext=fontfile='$font_bold':text='PHASE 1  |  BUILD THE CONVEYOR':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=645,
         drawtext=fontfile='$font_regular':text='Establish reliable cube transport':fontcolor=0x58d6ff:fontsize=22:x=(w-text_w)/2:y=683[p1];
    [2:v]trim=start=5:end=30,setpts=(PTS-STARTPTS)/1.5,fps=30,scale=960:720,pad=1280:720:160:0:color=0x07111f,
         drawbox=x=0:y=625:w=1280:h=95:color=0x07111f@0.94:t=fill,
         drawtext=fontfile='$font_bold':text='PHASE 2  |  ADD ROBOT CONTROL':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=645,
         drawtext=fontfile='$font_regular':text='The SO-101 pushes a selected cube':fontcolor=0x58d6ff:fontsize=22:x=(w-text_w)/2:y=683[p2];
    [3:v]trim=start=5:end=35,setpts=(PTS-STARTPTS)/1.5,fps=30,scale=960:720,pad=1280:720:160:0:color=0x07111f,
         drawbox=x=0:y=625:w=1280:h=95:color=0x07111f@0.94:t=fill,
         drawtext=fontfile='$font_bold':text='PHASE 3  |  LET CODEX CHOOSE':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=645,
         drawtext=fontfile='$font_regular':text='Follow a language rule and reject blue':fontcolor=0x58d6ff:fontsize=22:x=(w-text_w)/2:y=683[p3];
    [4:v]trim=start=5:end=45,setpts=(PTS-STARTPTS)/1.5,fps=30,scale=960:720,pad=1280:720:160:0:color=0x07111f,
         drawbox=x=0:y=625:w=1280:h=95:color=0x07111f@0.94:t=fill,
         drawtext=fontfile='$font_bold':text='PHASE 4  |  KEEP TIME MOVING':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=645,
         drawtext=fontfile='$font_regular':text='Plan actions on a continuous conveyor':fontcolor=0x58d6ff:fontsize=22:x=(w-text_w)/2:y=683[p4];
    [5:v]trim=start=10:end=75,setpts=(PTS-STARTPTS)/2,fps=30,scale=960:720,pad=1280:720:160:0:color=0x07111f,
         drawbox=x=0:y=625:w=1280:h=95:color=0x07111f@0.94:t=fill,
         drawtext=fontfile='$font_bold':text='PHASE 5  |  ADD CAMERA VISION':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=645,
         drawtext=fontfile='$font_regular':text='Select the target from rendered pixels':fontcolor=0x58d6ff:fontsize=22:x=(w-text_w)/2:y=683[p5];
    [6:v]trim=start=5:end=90,setpts=(PTS-STARTPTS)/2,fps=30,scale=960:720,pad=1280:720:160:0:color=0x07111f,
         drawbox=x=0:y=625:w=1280:h=95:color=0x07111f@0.94:t=fill,
         drawtext=fontfile='$font_bold':text='PHASE 6  |  MULTI-COLOR SORTING':fontcolor=white:fontsize=30:x=(w-text_w)/2:y=645,
         drawtext=fontfile='$font_regular':text='Reject red and blue. Let green pass.':fontcolor=0x58d6ff:fontsize=22:x=(w-text_w)/2:y=683[p6];
    [7:v]drawtext=fontfile='$font_bold':text='ONE ROBOT. SIX STEPS.':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=260,
         drawtext=fontfile='$font_regular':text='From transport to vision-guided language control':fontcolor=0x58d6ff:fontsize=28:x=(w-text_w)/2:y=340[outro];
    [intro][p1][p2][p3][p4][p5][p6][outro]concat=n=8:v=1:a=0[outv]
  " \
  -map '[outv]' -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -movflags +faststart "$output_dir/mujoco_llm_progression_linkedin.mp4"

ffmpeg -y -v warning \
  -f lavfi -i 'color=c=0x07111f:s=1080x1920:r=30:d=2.5' \
  -i "${sources[1]}" -i "${sources[2]}" -i "${sources[3]}" \
  -i "${sources[4]}" -i "${sources[5]}" -i "${sources[6]}" \
  -f lavfi -i 'color=c=0x07111f:s=1080x1920:r=30:d=3.5' \
  -filter_complex "
    [0:v]drawtext=fontfile='$font_bold':text='CAN AN LLM':fontcolor=white:fontsize=62:x=(w-text_w)/2:y=700,
         drawtext=fontfile='$font_bold':text='CONTROL A ROBOT?':fontcolor=white:fontsize=62:x=(w-text_w)/2:y=790,
         drawtext=fontfile='$font_regular':text='Six phases in MuJoCo':fontcolor=0x58d6ff:fontsize=40:x=(w-text_w)/2:y=930[intro];
    [1:v]trim=start=0:end=20,setpts=(PTS-STARTPTS)/2.5,fps=30,scale=1080:810,pad=1080:1920:0:555:color=0x07111f,
         drawtext=fontfile='$font_bold':text='PHASE 1':fontcolor=0x58d6ff:fontsize=48:x=(w-text_w)/2:y=215,
         drawtext=fontfile='$font_bold':text='BUILD THE CONVEYOR':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=285,
         drawtext=fontfile='$font_regular':text='Reliable cube transport':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=1450[p1];
    [2:v]trim=start=5:end=30,setpts=(PTS-STARTPTS)/3,fps=30,scale=1080:810,pad=1080:1920:0:555:color=0x07111f,
         drawtext=fontfile='$font_bold':text='PHASE 2':fontcolor=0x58d6ff:fontsize=48:x=(w-text_w)/2:y=215,
         drawtext=fontfile='$font_bold':text='ADD ROBOT CONTROL':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=285,
         drawtext=fontfile='$font_regular':text='SO-101 pushes a selected cube':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=1450[p2];
    [3:v]trim=start=5:end=35,setpts=(PTS-STARTPTS)/3,fps=30,scale=1080:810,pad=1080:1920:0:555:color=0x07111f,
         drawtext=fontfile='$font_bold':text='PHASE 3':fontcolor=0x58d6ff:fontsize=48:x=(w-text_w)/2:y=215,
         drawtext=fontfile='$font_bold':text='LET CODEX CHOOSE':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=285,
         drawtext=fontfile='$font_regular':text='Language rule\: reject blue':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=1450[p3];
    [4:v]trim=start=5:end=45,setpts=(PTS-STARTPTS)/4,fps=30,scale=1080:810,pad=1080:1920:0:555:color=0x07111f,
         drawtext=fontfile='$font_bold':text='PHASE 4':fontcolor=0x58d6ff:fontsize=48:x=(w-text_w)/2:y=215,
         drawtext=fontfile='$font_bold':text='KEEP TIME MOVING':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=285,
         drawtext=fontfile='$font_regular':text='Act on a continuous conveyor':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=1450[p4];
    [5:v]trim=start=10:end=70,setpts=(PTS-STARTPTS)/5,fps=30,scale=1080:810,pad=1080:1920:0:555:color=0x07111f,
         drawtext=fontfile='$font_bold':text='PHASE 5':fontcolor=0x58d6ff:fontsize=48:x=(w-text_w)/2:y=215,
         drawtext=fontfile='$font_bold':text='ADD CAMERA VISION':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=285,
         drawtext=fontfile='$font_regular':text='Choose targets from pixels':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=1450[p5];
    [6:v]trim=start=5:end=90,setpts=(PTS-STARTPTS)/5,fps=30,scale=1080:810,pad=1080:1920:0:555:color=0x07111f,
         drawtext=fontfile='$font_bold':text='PHASE 6':fontcolor=0x58d6ff:fontsize=48:x=(w-text_w)/2:y=215,
         drawtext=fontfile='$font_bold':text='MULTI-COLOR SORTING':fontcolor=white:fontsize=54:x=(w-text_w)/2:y=285,
         drawtext=fontfile='$font_regular':text='Reject red + blue. Pass green.':fontcolor=white:fontsize=38:x=(w-text_w)/2:y=1450[p6];
    [7:v]drawtext=fontfile='$font_bold':text='FROM MOTION':fontcolor=white:fontsize=62:x=(w-text_w)/2:y=700,
         drawtext=fontfile='$font_bold':text='TO LANGUAGE + VISION':fontcolor=white:fontsize=56:x=(w-text_w)/2:y=790,
         drawtext=fontfile='$font_regular':text='SO-101 simulated in MuJoCo':fontcolor=0x58d6ff:fontsize=38:x=(w-text_w)/2:y=930[outro];
    [intro][p1][p2][p3][p4][p5][p6][outro]concat=n=8:v=1:a=0[outv]
  " \
  -map '[outv]' -c:v libx264 -preset medium -crf 20 -pix_fmt yuv420p \
  -movflags +faststart "$output_dir/mujoco_llm_progression_youtube_short.mp4"

print "Created:"
print "$output_dir/mujoco_llm_progression_linkedin.mp4"
print "$output_dir/mujoco_llm_progression_youtube_short.mp4"
