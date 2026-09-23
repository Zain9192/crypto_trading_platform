import numpy as np


def baseline(values, names):
    values=np.asarray(values,dtype=float)
    if values.ndim!=2 or values.shape[1]!=len(names) or len(values)<100 or not np.isfinite(values).all():
        raise ValueError('Drift baseline requires at least 100 finite training rows')
    result={}
    for i,name in enumerate(names):
        cuts=np.unique(np.quantile(values[:,i],np.linspace(.1,.9,9)))
        bins=np.r_[-np.inf,cuts,np.inf]
        counts=np.histogram(values[:,i],bins=bins)[0]
        result[name]={'cuts':cuts.tolist(),'proportions':(counts/len(values)).tolist()}
    return result


def assess(values, names, reference):
    values=np.asarray(values,dtype=float)
    if not reference:
        return {'status':'baseline_unavailable','features':{}}
    if values.ndim!=2 or len(values)<100 or not np.isfinite(values).all():
        return {'status':'insufficient_data','features':{}}
    scores={}
    for i,name in enumerate(names):
        spec=reference.get(name)
        if not spec:
            return {'status':'baseline_unavailable','features':{}}
        actual=np.histogram(values[:,i],bins=np.r_[-np.inf,spec['cuts'],np.inf])[0]/len(values)
        expected=np.asarray(spec['proportions'])
        a,e=np.maximum(actual,1e-6),np.maximum(expected,1e-6)
        scores[name]=float(np.sum((a-e)*np.log(a/e)))
    return {'status':'review' if max(scores.values(),default=0)>.25 else 'stable',
            'features':scores,'method':'PSI','review_threshold':.25,'sample_count':len(values)}
