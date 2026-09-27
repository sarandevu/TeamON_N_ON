# EdgePPG Training Videos

Place your mobile video recordings here:

## Folder Layout

`
data/videos/
  LIVE/
    <subject_name>_<session>.mp4    ← person recording themselves for real VKYC
    S001_v01.mp4
    S002_v01.mp4
  SPOOF/
    <subject_name>_<session>.mp4    ← screen replay / printed photo attack
    S003_v01.mp4
`

## Then run ingestion:

`powershell
# Step 1: Extract features from all videos
python -m ml.src.ingest_videos data/videos/ --label-mode subfolder

# Step 2: Train RF model on the extracted real data
python -m ml.src.train_rf --data-source raw --out models/

# Step 3: Train XGB challenger model
python -m ml.src.train_xgb --data-source raw --out models/
`

## Video Requirements
- Format: MP4, MOV, AVI, MKV  
- Duration: at least 3 seconds (90+ frames recommended)
- Resolution: any (720p or higher preferred)
- Content: face clearly visible, well lit
- LIVE: person speaking/blinking naturally
- SPOOF: phone/tablet/laptop screen showing the person's photo or video
