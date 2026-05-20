def classify_confidence(score):
    if score < 50:
        return "Verify This"
    elif score < 80:
        return "Moderate Confidence"
    return "High Confidence"