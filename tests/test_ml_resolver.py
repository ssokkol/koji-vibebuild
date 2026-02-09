"""Tests for vibebuild.ml_resolver module."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from vibebuild.ml_resolver import MLPackageResolver, HAS_SKLEARN


# Sample training data that mimics real Fedora provides
SAMPLE_TRAINING_DATA = [
    {"provide": "python3dist(requests)", "rpm_name": "python3-requests", "srpm_name": "python-requests"},
    {"provide": "python3dist(urllib3)", "rpm_name": "python3-urllib3", "srpm_name": "python-urllib3"},
    {"provide": "python3dist(setuptools)", "rpm_name": "python3-setuptools", "srpm_name": "python-setuptools"},
    {"provide": "python3dist(pip)", "rpm_name": "python3-pip", "srpm_name": "python-pip"},
    {"provide": "python3dist(numpy)", "rpm_name": "python3-numpy", "srpm_name": "numpy"},
    {"provide": "python3dist(flask)", "rpm_name": "python3-flask", "srpm_name": "python-flask"},
    {"provide": "python3dist(jinja2)", "rpm_name": "python3-jinja2", "srpm_name": "python-jinja2"},
    {"provide": "pkgconfig(glib-2.0)", "rpm_name": "glib2-devel", "srpm_name": "glib2"},
    {"provide": "pkgconfig(gtk+-3.0)", "rpm_name": "gtk3-devel", "srpm_name": "gtk3"},
    {"provide": "pkgconfig(libxml-2.0)", "rpm_name": "libxml2-devel", "srpm_name": "libxml2"},
    {"provide": "pkgconfig(openssl)", "rpm_name": "openssl-devel", "srpm_name": "openssl"},
    {"provide": "pkgconfig(zlib)", "rpm_name": "zlib-devel", "srpm_name": "zlib"},
    {"provide": "perl(strict)", "rpm_name": "perl-interpreter", "srpm_name": "perl"},
    {"provide": "perl(File::Path)", "rpm_name": "perl-File-Path", "srpm_name": "perl-File-Path"},
    {"provide": "perl(JSON::PP)", "rpm_name": "perl-JSON-PP", "srpm_name": "perl-JSON-PP"},
    {"provide": "cmake(Qt5Core)", "rpm_name": "qt5-qtbase-devel", "srpm_name": "qt5-qtbase"},
    {"provide": "golang(github.com/stretchr/testify)", "rpm_name": "golang-github-stretchr-testify-devel", "srpm_name": "golang-github-stretchr-testify"},
    {"provide": "rubygem(rake)", "rpm_name": "rubygem-rake", "srpm_name": "rubygem-rake"},
    {"provide": "npm(express)", "rpm_name": "nodejs-express", "srpm_name": "nodejs-express"},
    {"provide": "python3dist(click)", "rpm_name": "python3-click", "srpm_name": "python-click"},
]


@pytest.fixture
def training_data():
    """Sample training data for testing."""
    return SAMPLE_TRAINING_DATA.copy()


@pytest.fixture
def trained_resolver(training_data):
    """MLPackageResolver with a trained model (no model file on disk)."""
    resolver = MLPackageResolver.__new__(MLPackageResolver)
    resolver.confidence_threshold = 0.3
    resolver._vectorizer = None
    resolver._nn_model = None
    resolver._rpm_names = []
    resolver._srpm_names = []
    resolver._provides = []
    resolver._model_loaded = False
    resolver._cache = {}
    resolver._cache_dirty = False
    resolver.train(training_data)
    return resolver


@pytest.fixture
def empty_resolver():
    """MLPackageResolver without a loaded model."""
    resolver = MLPackageResolver.__new__(MLPackageResolver)
    resolver.confidence_threshold = 0.3
    resolver._vectorizer = None
    resolver._nn_model = None
    resolver._rpm_names = []
    resolver._srpm_names = []
    resolver._provides = []
    resolver._model_loaded = False
    resolver._cache = {}
    resolver._cache_dirty = False
    return resolver


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverInstantiation:
    def test_can_instantiate_without_model(self):
        """MLPackageResolver should instantiate even if no model file exists."""
        resolver = MLPackageResolver(model_path="/nonexistent/path/model.joblib")

        assert resolver is not None
        assert resolver.confidence_threshold == 0.3
        assert resolver._model_loaded is False

    def test_can_instantiate_with_default_path(self):
        """MLPackageResolver should instantiate with default model path."""
        resolver = MLPackageResolver()

        assert resolver is not None
        assert resolver.confidence_threshold == 0.3


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverTrain:
    def test_train_on_sample_data(self, training_data):
        """Model should train successfully on sample data."""
        resolver = MLPackageResolver.__new__(MLPackageResolver)
        resolver.confidence_threshold = 0.3
        resolver._vectorizer = None
        resolver._nn_model = None
        resolver._rpm_names = []
        resolver._srpm_names = []
        resolver._provides = []
        resolver._model_loaded = False
        resolver._cache = {}
        resolver._cache_dirty = False

        resolver.train(training_data)

        assert resolver._model_loaded is True
        assert len(resolver._provides) == len(training_data)
        assert len(resolver._rpm_names) == len(training_data)
        assert len(resolver._srpm_names) == len(training_data)
        assert resolver._vectorizer is not None
        assert resolver._nn_model is not None

    def test_train_empty_data_raises(self, empty_resolver):
        """Training with empty data should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            empty_resolver.train([])

    def test_train_sets_vocabulary(self, trained_resolver):
        """After training, vectorizer should have a vocabulary."""
        vocab = trained_resolver._vectorizer.vocabulary_
        assert len(vocab) > 0


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverPredict:
    def test_predict_exact_match(self, trained_resolver):
        """Predicting an exact training provide should return correct result."""
        result = trained_resolver.predict("python3dist(requests)")

        assert result is not None
        assert result["rpm_name"] == "python3-requests"
        assert result["srpm_name"] == "python-requests"

    def test_predict_pkgconfig_match(self, trained_resolver):
        """Predicting a pkgconfig provide should return correct result."""
        result = trained_resolver.predict("pkgconfig(glib-2.0)")

        assert result is not None
        assert result["rpm_name"] == "glib2-devel"
        assert result["srpm_name"] == "glib2"

    def test_predict_perl_match(self, trained_resolver):
        """Predicting a perl provide should return correct result."""
        result = trained_resolver.predict("perl(JSON::PP)")

        assert result is not None
        assert result["rpm_name"] == "perl-JSON-PP"

    def test_predict_returns_none_for_garbage(self, trained_resolver):
        """Predicting totally unrelated input should return None (low confidence)."""
        # Use something very different from training data
        result = trained_resolver.predict("xxxxxxxxx_yyyyyyyy_zzzzzzz_12345")

        assert result is None

    def test_predict_returns_none_when_not_available(self, empty_resolver):
        """Predicting without a loaded model should return None."""
        result = empty_resolver.predict("python3dist(requests)")

        assert result is None

    def test_predict_result_structure(self, trained_resolver):
        """Prediction result should have rpm_name and srpm_name keys."""
        result = trained_resolver.predict("python3dist(flask)")

        assert result is not None
        assert "rpm_name" in result
        assert "srpm_name" in result
        assert isinstance(result["rpm_name"], str)
        assert isinstance(result["srpm_name"], str)


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverSaveLoad:
    def test_save_and_load_roundtrip(self, trained_resolver, tmp_path):
        """Model should produce same predictions after save/load cycle."""
        model_file = tmp_path / "test_model.joblib"

        # Save
        trained_resolver.save(str(model_file))
        assert model_file.exists()

        # Load into new resolver
        loaded = MLPackageResolver.__new__(MLPackageResolver)
        loaded.confidence_threshold = 0.3
        loaded._vectorizer = None
        loaded._nn_model = None
        loaded._rpm_names = []
        loaded._srpm_names = []
        loaded._provides = []
        loaded._model_loaded = False
        loaded._cache = {}
        loaded._cache_dirty = False
        loaded.load(str(model_file))

        # Compare predictions
        original_result = trained_resolver.predict("python3dist(requests)")
        loaded_result = loaded.predict("python3dist(requests)")

        assert original_result is not None
        assert loaded_result is not None
        assert original_result["rpm_name"] == loaded_result["rpm_name"]
        assert original_result["srpm_name"] == loaded_result["srpm_name"]

    def test_save_creates_parent_dirs(self, trained_resolver, tmp_path):
        """Save should create parent directories if they don't exist."""
        model_file = tmp_path / "nested" / "dir" / "model.joblib"

        trained_resolver.save(str(model_file))

        assert model_file.exists()

    def test_save_raises_without_trained_model(self, empty_resolver, tmp_path):
        """Save should raise if no model is trained."""
        model_file = tmp_path / "model.joblib"

        with pytest.raises(RuntimeError, match="No model to save"):
            empty_resolver.save(str(model_file))

    def test_load_nonexistent_file_raises(self, empty_resolver):
        """Load should raise FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Model file not found"):
            empty_resolver.load("/nonexistent/model.joblib")

    def test_load_via_constructor(self, trained_resolver, tmp_path):
        """Constructor should auto-load model if path exists."""
        model_file = tmp_path / "model.joblib"
        trained_resolver.save(str(model_file))

        resolver = MLPackageResolver(model_path=str(model_file))

        assert resolver.is_available() is True
        result = resolver.predict("python3dist(requests)")
        assert result is not None
        assert result["rpm_name"] == "python3-requests"


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverIsAvailable:
    def test_is_available_after_training(self, trained_resolver):
        """is_available should return True after training."""
        assert trained_resolver.is_available() is True

    def test_is_available_without_model(self, empty_resolver):
        """is_available should return False when no model is loaded."""
        assert empty_resolver.is_available() is False

    def test_is_available_after_load(self, trained_resolver, tmp_path):
        """is_available should return True after loading a saved model."""
        model_file = tmp_path / "model.joblib"
        trained_resolver.save(str(model_file))

        resolver = MLPackageResolver.__new__(MLPackageResolver)
        resolver.confidence_threshold = 0.3
        resolver._vectorizer = None
        resolver._nn_model = None
        resolver._rpm_names = []
        resolver._srpm_names = []
        resolver._provides = []
        resolver._model_loaded = False
        resolver._cache = {}
        resolver._cache_dirty = False

        assert resolver.is_available() is False

        resolver.load(str(model_file))

        assert resolver.is_available() is True


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverCache:
    def test_prediction_is_cached(self, trained_resolver):
        """After a prediction, the result should be in the cache."""
        trained_resolver._cache = {}

        result = trained_resolver.predict("python3dist(requests)")

        assert result is not None
        assert len(trained_resolver._cache) == 1
        # Second call should use cache
        cache_key = trained_resolver._cache_key("python3dist(requests)")
        assert cache_key in trained_resolver._cache
        assert trained_resolver._cache[cache_key] == result

    def test_cached_prediction_returns_same_result(self, trained_resolver):
        """Subsequent predictions for the same input should return cached results."""
        trained_resolver._cache = {}

        result1 = trained_resolver.predict("pkgconfig(glib-2.0)")
        result2 = trained_resolver.predict("pkgconfig(glib-2.0)")

        assert result1 == result2

    def test_cache_persists_to_disk(self, trained_resolver, tmp_path, mocker):
        """Cache should be written to disk after prediction."""
        cache_file = tmp_path / "test_cache.json"
        mocker.patch("vibebuild.ml_resolver._CACHE_FILE", cache_file)
        mocker.patch("vibebuild.ml_resolver._CACHE_DIR", tmp_path)
        trained_resolver._cache = {}
        trained_resolver._cache_dirty = False

        trained_resolver.predict("python3dist(requests)")

        assert cache_file.exists()
        with open(cache_file, "r") as f:
            disk_cache = json.load(f)
        assert len(disk_cache) == 1

    def test_cache_loads_from_disk(self, trained_resolver, tmp_path, mocker):
        """Cache should be loaded from disk on initialization."""
        cache_file = tmp_path / "test_cache.json"
        cache_data = {"abc123": {"rpm_name": "cached-pkg", "srpm_name": "cached-src"}}
        with open(cache_file, "w") as f:
            json.dump(cache_data, f)

        mocker.patch("vibebuild.ml_resolver._CACHE_FILE", cache_file)
        trained_resolver._load_cache()

        assert "abc123" in trained_resolver._cache
        assert trained_resolver._cache["abc123"]["rpm_name"] == "cached-pkg"

    def test_cache_handles_corrupt_file(self, tmp_path, mocker):
        """Cache loading should handle corrupt JSON gracefully."""
        cache_file = tmp_path / "bad_cache.json"
        cache_file.write_text("not valid json {{{")

        mocker.patch("vibebuild.ml_resolver._CACHE_FILE", cache_file)

        resolver = MLPackageResolver.__new__(MLPackageResolver)
        resolver._cache = {}
        resolver._cache_dirty = False
        resolver._load_cache()

        assert resolver._cache == {}


@pytest.mark.skipif(not HAS_SKLEARN, reason="scikit-learn not installed")
class TestMLPackageResolverWithoutSklearn:
    def test_train_raises_without_sklearn(self, mocker):
        """Training should raise RuntimeError if sklearn is not available."""
        mocker.patch("vibebuild.ml_resolver.HAS_SKLEARN", False)

        resolver = MLPackageResolver.__new__(MLPackageResolver)
        resolver.confidence_threshold = 0.3
        resolver._vectorizer = None
        resolver._nn_model = None
        resolver._rpm_names = []
        resolver._srpm_names = []
        resolver._provides = []
        resolver._model_loaded = False
        resolver._cache = {}
        resolver._cache_dirty = False

        with pytest.raises(RuntimeError, match="scikit-learn is required"):
            resolver.train(SAMPLE_TRAINING_DATA)

    def test_is_available_false_without_sklearn(self, mocker):
        """is_available should return False when sklearn is not available."""
        mocker.patch("vibebuild.ml_resolver.HAS_SKLEARN", False)

        resolver = MLPackageResolver.__new__(MLPackageResolver)
        resolver._model_loaded = True  # Even with model "loaded"
        resolver._cache = {}
        resolver._cache_dirty = False

        assert resolver.is_available() is False
