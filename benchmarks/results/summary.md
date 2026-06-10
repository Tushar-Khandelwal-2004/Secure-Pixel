# SecurePixel Benchmark Summary

## Detection Rate by Attack Type

| Attack type | SecurePixel | ImageHash | SSIM | OpenCV template | Samples |
|---|---:|---:|---:|---:|---:|
| ai_upscale_simulation | 100.0% | 100.0% | 100.0% | 100.0% | 60 |
| brightness | 98.3% | 100.0% | 100.0% | 100.0% | 60 |
| combined_attack | 100.0% | 48.9% | 42.2% | 28.9% | 90 |
| contrast | 100.0% | 100.0% | 100.0% | 100.0% | 60 |
| crop | 100.0% | 15.6% | 11.1% | 54.4% | 90 |
| flip | 100.0% | 3.3% | 6.7% | 5.0% | 60 |
| format_conversion | 98.3% | 100.0% | 100.0% | 100.0% | 60 |
| gaussian_noise | 97.8% | 100.0% | 100.0% | 100.0% | 90 |
| generative_fill_simulation | 96.7% | 100.0% | 100.0% | 100.0% | 60 |
| jpeg_compression | 97.5% | 100.0% | 100.0% | 100.0% | 120 |
| resize | 100.0% | 100.0% | 100.0% | 50.0% | 90 |
| saturation | 98.3% | 100.0% | 100.0% | 100.0% | 60 |
| screenshot_simulation | 100.0% | 100.0% | 100.0% | 100.0% | 30 |

## Leaderboard

| Rank | System | Detection rate |
|---:|---|---:|
| 1 | securepixel | 98.9% |
| 2 | imagehash | 80.7% |
| 3 | ssim | 79.8% |
| 4 | opencv_template | 77.7% |

## SecurePixel Layer Contribution

| Layer | Count |
|---|---:|
| unknown | 31 |
| embedding_similarity | 90 |
| perceptual_hash | 584 |
| watermark | 215 |
