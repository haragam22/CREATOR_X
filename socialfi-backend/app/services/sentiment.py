import logging
import math
import traceback
from transformers import pipeline

logger = logging.getLogger(__name__)

logger.info("Loading Hugging Face sentiment pipeline (Twitter RoBERTa)...")
try:
    sentiment_pipeline = pipeline(
        "text-classification",
        model="cardiffnlp/twitter-roberta-base-sentiment-latest",
        use_safetensors=True
    )
    logger.info("Sentiment pipeline loaded successfully.")
except Exception as e:
    logger.error(f"Failed to load sentiment pipeline: {e}")
    logger.error(traceback.format_exc())  # Full traceback for debugging
    sentiment_pipeline = None


def compute_modifier(comments: list[str]) -> int:
    """
    Computes a market modifier based on NLP sentiment analysis of comments.
    Returns: BPS integer (10000 = 1.0 = neutral)
    """
    if not comments or sentiment_pipeline is None:
        return 10000

    # 2. Add a comment pre-filter
    filtered_comments = []
    drop_phrases = ["subscribe back", "check my channel", "first!", "www."]
    
    for c in comments:
        # Drop comments shorter than 10 characters
        if len(c) < 10:
            continue
        # Drop all-caps comments
        if c.isupper():
            continue
            
        c_lower = c.lower()
        if any(phrase in c_lower for phrase in drop_phrases):
            continue
            
        filtered_comments.append(c)

    if not filtered_comments:
        return 10000

    # Run pipeline
    results = sentiment_pipeline(filtered_comments, truncation=True, max_length=512)
    
    # 3. Rewrite compute_modifier()
    # Model classes: 'positive', 'neutral', 'negative'
    pos_score_sum = 0.0
    neg_score_sum = 0.0
    opinionated_count = 0
    
    for result in results:
        label = result['label'].lower()
        score = result['score']
        
        if label == 'positive':
            pos_score_sum += score
            opinionated_count += 1
        elif label == 'negative':
            neg_score_sum += score
            opinionated_count += 1
        # Drop neutral entirely

    # If fewer than 5 opinionated comments remain after filtering, return 10000
    if opinionated_count < 5:
        logger.info(f"Only {opinionated_count} opinionated comments. Defaulting to neutral (10000 BPS).")
        return 10000
        
    net = (pos_score_sum - neg_score_sum) / opinionated_count
    modifier = 1.0 + (net * 0.5)
    
    modifier_bps = int(modifier * 10000)
    # Clamp just in case
    modifier_bps = max(5000, min(15000, modifier_bps))
    
    logger.info(f"Sentiment Analysis: {opinionated_count} opinionated comments. Net: {net:.2f}. BPS: {modifier_bps}")
    return modifier_bps


def compute_engagement_score(channel_metrics: dict) -> float:
    """
    4. Add compute_engagement_score()
    Takes the channel_metrics dict. Returns a float 0.0-1.0.
    """
    avg_comments = channel_metrics.get("avg_comments", 0)
    avg_views = channel_metrics.get("avg_views", 1)  # avoid div by zero
    avg_likes = channel_metrics.get("avg_likes", 0)
    videos_last_90d = channel_metrics.get("videos_last_90d", 0)
    
    if avg_views <= 0:
        avg_views = 1

    comment_rate = avg_comments / avg_views
    like_rate = avg_likes / avg_views
    upload_velocity = min(videos_last_90d / 12.0, 1.0)
    
    score = (comment_rate * 0.4) + (like_rate * 0.4) + (upload_velocity * 0.2)
    return min(score, 1.0)


def creator_rank_score(creator: dict) -> float:
    """
    5. Add creator_rank_score()
    Used by GET /creators to sort the marketplace listing.
    Takes a creator dict with fields: ai_modifier_bps, engagement_score, days_since_last_upload, subscriber_count.
    Returns a float.
    """
    ai_modifier_bps = creator.get("ai_modifier_bps", 10000)
    engagement_score = creator.get("engagement_score", 0.0)
    days_since_last_upload = creator.get("days_since_last_upload", 999)
    subscriber_count = creator.get("subscriber_count", 0)
    
    sentiment_norm = (ai_modifier_bps - 5000) / 10000.0
    upload_recency = 1.0 if days_since_last_upload < 14 else 0.3
    subscriber_norm = math.log10(max(subscriber_count, 1)) / 7.0
    
    score = (
        (sentiment_norm * 0.40) +
        (engagement_score * 0.35) +
        (upload_recency * 0.15) +
        (subscriber_norm * 0.10)
    )
    return score
