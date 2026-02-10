import json
import sys
import subprocess
from cat.log import log
from cat.mad_hatter.decorators import hook

# Global variables for spaCy model
_spacy_model = None
_spacy_available = None

def _check_spacy_availability() -> bool:
    """Check if spaCy is available."""
    global _spacy_available
    if _spacy_available is not None:
        return _spacy_available
    
    try:
        import spacy
        _spacy_available = True
    except ImportError:
        log.warning(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "import_error",
            "data": {
                "message": "spaCy not installed. Install with: pip install spacy"
            }
        }))
        _spacy_available = False
    
    return _spacy_available

def _download_model(model_name: str) -> bool:
    """Download a spaCy model if not present."""
    try:
        log.info(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_download_start",
            "data": {
                "model_name": model_name
            }
        }))
        
        result = subprocess.run([
            sys.executable, "-m", "spacy", "download", model_name
        ], capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_download_success",
                "data": {
                    "model_name": model_name
                }
            }))
            return True
        else:
            log.error(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_download_error",
                "data": {
                    "model_name": model_name,
                    "error": result.stderr
                }
            }))
            return False
    except subprocess.TimeoutExpired:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_download_timeout",
            "data": {
                "model_name": model_name
            }
        }))
        return False
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_download_error",
            "data": {
                "model_name": model_name,
                "error": str(e)
            }
        }))
        return False

def _get_spacy_model(model_name: str):
    """Get or load a spaCy model, downloading if necessary."""
    global _spacy_model
    
    if _spacy_model:
        return _spacy_model
    
    if not _check_spacy_availability():
        return None
    
    try:
        import spacy
        
        # First try to load the model
        try:
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_load_start",
                "data": {
                    "model_name": model_name
                }
            }))
            
            nlp = spacy.load(model_name)
            
            # Add sentiment analysis component using spacytextblob
            try:
                from spacytextblob.spacytextblob import SpacyTextBlob
                if 'spacytextblob' not in nlp.pipe_names:
                    nlp.add_pipe('spacytextblob')
                    log.info(json.dumps({
                        "component": "ccat_oc_analytics",
                        "event": "sentiment_component_added",
                        "data": {
                            "model_name": model_name
                        }
                    }))
            except ImportError:
                log.warning(json.dumps({
                    "component": "ccat_oc_analytics",
                    "event": "spacytextblob_not_found",
                    "data": {
                        "message": "spacytextblob not installed. Install with: pip install spacytextblob"
                    }
                }))
            
            _spacy_model = nlp
            
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_load_success",
                "data": {
                    "model_name": model_name
                }
            }))
            return nlp
        except OSError:
            # Model not found, try to download it
            log.info(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "model_not_found",
                "data": {
                    "model_name": model_name,
                    "message": "Attempting to download..."
                }
            }))
            
            if _download_model(model_name):
                # Try loading again after download
                try:
                    nlp = spacy.load(model_name)
                    
                    # Add sentiment analysis component using spacytextblob
                    try:
                        from spacytextblob.spacytextblob import SpacyTextBlob
                        if 'spacytextblob' not in nlp.pipe_names:
                            nlp.add_pipe('spacytextblob')
                    except ImportError:
                        log.warning(json.dumps({
                            "component": "ccat_oc_analytics",
                            "event": "spacytextblob_not_found",
                            "data": {
                                "message": "spacytextblob not installed. Install with: pip install spacytextblob"
                            }
                        }))
                    
                    _spacy_model = nlp
                    log.info(json.dumps({
                        "component": "ccat_oc_analytics",
                        "event": "model_load_success",
                        "data": {
                            "model_name": model_name,
                            "after_download": True
                        }
                    }))
                    return nlp
                except OSError:
                    log.error(json.dumps({
                        "component": "ccat_oc_analytics",
                        "event": "model_load_error",
                        "data": {
                            "model_name": model_name,
                            "error": "Failed to load even after download"
                        }
                    }))
                    return None
            else:
                return None
    except Exception as e:
        log.error(json.dumps({
            "component": "ccat_oc_analytics",
            "event": "model_load_error",
            "data": {
                "error": str(e)
            }
        }))
        return None

def analyze_sentiment(text: str):
    """Analyze sentiment using spaCy with spacytextblob.
    
    Returns polarity score from -1 (negative) to 1 (positive).
    Uses TextBlob sentiment analysis via spacytextblob extension.
    """
    model_name = "xx_sent_ud_sm"
    nlp = _get_spacy_model(model_name)
    
    if nlp:
        try:
            # Truncate text to avoid processing very long texts
            if len(text) > 2000:
                text = text[:2000]
            
            doc = nlp(text)
            
            # spacytextblob provides polarity in doc._.polarity (ranges from -1 to 1)
            # and subjectivity in doc._.subjectivity (ranges from 0 to 1)
            if hasattr(doc._, 'polarity'):
                polarity = doc._.polarity
                # Ensure the value is within expected range
                return max(-1.0, min(1.0, polarity))
            else:
                # Fallback: calculate average polarity from sentences
                if doc.sents:
                    polarities = [
                        sent._.polarity if hasattr(sent._, 'polarity') else 0.0 
                        for sent in doc.sents
                    ]
                    if polarities:
                        avg_polarity = sum(polarities) / len(polarities)
                        return max(-1.0, min(1.0, avg_polarity))
                return 0.0
            
        except Exception as e:
            log.error(json.dumps({
                "component": "ccat_oc_analytics",
                "event": "sentiment_analysis_error",
                "data": {
                    "error": str(e)
                }
            }))
            return 0.0
    return 0.0


@hook
def after_cat_bootstrap(cat):
    # Pre-download the SpaCy model for sentiment analysis
    _get_spacy_model("xx_sent_ud_sm")
