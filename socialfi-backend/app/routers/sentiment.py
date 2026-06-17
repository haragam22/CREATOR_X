"""
Sentiment Analysis Router — /sentiment
=======================================
Exposes the full NLP pipeline as proper REST endpoints so the Flutter
frontend (and dashboard) can call them instead of importing backend modules.

Endpoints:
  POST /sentiment/analyze   — analyze a YouTube channel by channel_id
  GET  /sentiment/{creator_id} — get latest stored sentiment for a creator
"""
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sentiment", tags=["sentiment"])


class AnalyzeRequest(BaseModel):
    channel_id: str
    max_comments: int = 20


@router.post("/analyze")
async def analyze_channel(req: AnalyzeRequest):
    """
    Full pipeline:
      1. Fetch YouTube channel metrics (subscribers, tier)
      2. Fetch recent comments from the channel
      3. Run the RoBERTa NLP model to compute sentiment modifier BPS
      4. Compute engagement score and creator rank score
      5. Return the full breakdown

    This is the endpoint the Flutter frontend and Streamlit dashboard should call.
    """
    from app.services.youtube import YouTubeService
    from app.tasks.sentiment_tasks import fetch_youtube_comments
    from app.services.sentiment import compute_modifier, compute_engagement_score, creator_rank_score, sentiment_pipeline

    # --- Guard: make sure the model loaded properly ---
    if sentiment_pipeline is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "Sentiment model is not loaded. This is due to PyTorch safety compliance checks. "
                "Verify that app/services/sentiment.py is using use_safetensors=True."
            )
        )

    # 1. Fetch YouTube channel metrics
    try:
        metrics = await YouTubeService.get_channel_metrics(req.channel_id)
    except HTTPException as e:
        raise e
    except Exception as e:
        logger.error(f"YouTube API error for {req.channel_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to fetch YouTube data: {str(e)}")

    # 2. Fetch comments
    comments = await fetch_youtube_comments(req.channel_id, max_results=req.max_comments)

    # 3. Run NLP
    modifier_bps = compute_modifier(comments)
    modifier_float = modifier_bps / 10000.0

    # 4. Compute supporting scores
    engagement = compute_engagement_score(metrics)
    mock_creator = {
        "ai_modifier_bps": modifier_bps,
        "engagement_score": engagement,
        "days_since_last_upload": 7,  # placeholder — would read from YT API in production
        "subscriber_count": metrics.get("subscribers", 0)
    }
    rank = creator_rank_score(mock_creator)

    # 5. Determine signal quality
    if modifier_bps == 10000 and len(comments) < 5:
        signal = "insufficient_data"
        signal_label = "Not enough opinionated comments (need ≥5)"
    elif modifier_float > 1.0:
        signal = "positive"
        signal_label = f"Bullish sentiment detected ({modifier_float:.3f}×)"
    elif modifier_float < 1.0:
        signal = "negative"
        signal_label = f"Bearish sentiment detected ({modifier_float:.3f}×)"
    else:
        signal = "neutral"
        signal_label = "Neutral — no strong opinion signal"

    return {
        "channel": {
            "id": req.channel_id,
            "name": metrics.get("channel_name", ""),
            "subscribers": metrics.get("subscribers", 0),
            "tier": metrics.get("tier", 0),
            "tier_name": ["Micro", "Mid", "Star"][metrics.get("tier", 0)],
            "base_price_usdc": metrics.get("base_price_usdc", 0),
            "k_value": metrics.get("k_value", 0),
        },
        "comments": {
            "fetched": len(comments),
            "sample": comments[:5],  # return first 5 as a preview
        },
        "sentiment": {
            "modifier_bps": modifier_bps,
            "modifier_float": round(modifier_float, 4),
            "signal": signal,
            "signal_label": signal_label,
        },
        "scores": {
            "engagement": round(engagement, 4),
            "creator_rank": round(rank, 4),
        }
    }


@router.get("/model/status")
async def model_status():
    """
    Checks if the HuggingFace sentiment model loaded correctly.
    Returns diagnostic info including the detected Python version.
    """
    import sys
    from app.services.sentiment import sentiment_pipeline

    py_version = sys.version
    model_ok = sentiment_pipeline is not None

    return {
        "model_loaded": model_ok,
        "python_version": py_version,
        "model_name": "cardiffnlp/twitter-roberta-base-sentiment-latest",
        "warning": (
            None if model_ok else
            "Model failed to load due to torch.load security restrictions. "
            "Ensure use_safetensors=True is passed or upgrade torch to >= 2.6.0."
        )
    }
