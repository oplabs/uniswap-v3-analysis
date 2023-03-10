import pickle

def deepcopy(obj):
	return pickle.loads(pickle.dumps(obj, -1))