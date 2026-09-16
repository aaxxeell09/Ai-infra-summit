import copy
import pytest
from turbo.feedback_binding import bound_config,verify_bound_config


def fixture():
    runtime={'schema_version':'turbo.runtime.v1','sha256':'sdk','files':{'a':'hash'}}
    rec={'model_id':'m','plugin':'llama_cpp','model_sha256':'weights','runtime_binding':runtime,
         'modes':{'fast':{'device':'cpu','threads':6,'context':4096}}}
    service={'sdk_dir':'sdk','models':{'m':{'path':'weights','plugin':'llama_cpp'}}}
    applied={'model':'m','mode':'fast','config':dict(rec['modes']['fast']),'evidence':{'provisional':True}}
    return service,rec,applied


def test_exact_binding_preserved():
    service,rec,applied=fixture();config=bound_config(service,rec,applied)
    assert config['threads']==6
    assert verify_bound_config(config,'weights',rec['runtime_binding'])
    assert config['recommendation_binding']['quality_qualified'] is False


@pytest.mark.parametrize('field,value',[('device','npu'),('threads',10),('context',1024),('plugin','qairt'),('ubatch',32),('spec_type','ngram'),('backend','qairt_npu'),('stop_after_tool_call',True)])
def test_drift_rejected(field,value):
    s,r,a=fixture();c=bound_config(s,r,a);c[field]=value
    with pytest.raises(ValueError):verify_bound_config(c,'weights',r['runtime_binding'])


def test_identity_and_apply_mismatch_rejected():
    s,r,a=fixture();c=bound_config(s,r,a)
    with pytest.raises(ValueError):verify_bound_config(c,'other',r['runtime_binding'])
    with pytest.raises(ValueError):verify_bound_config(c,'weights',{})
    a['config']['threads']=12
    with pytest.raises(ValueError):bound_config(s,r,a)
