import numpy as np
import pytest
from app.prediction.drift import baseline, assess


def test_shifted_distribution_requires_review():
    values=np.linspace(0,1,1000)[:,None]
    reference=baseline(values,['return'])
    assert assess(values,['return'],reference)['status']=='stable'
    assert assess(values+10,['return'],reference)['status']=='review'
    assert assess(values,['return'],None)['status']=='baseline_unavailable'
    assert assess(values[:10],['return'],reference)['status']=='insufficient_data'


def test_baseline_rejects_nonfinite_values():
    with pytest.raises(ValueError):
        baseline(np.full((100,1),np.nan),['return'])
