import joblib
import numpy as np

pipe = joblib.load("data/models/svm_pipeline.pkl")
tfidf = pipe.named_steps["tfidf"]
svm = pipe.named_steps["svm"]

terms = np.array(tfidf.get_feature_names_out())
classes = svm.classes_  # NEGATIF, NETRAL, POSITIF

pairs = [(0, 1), (0, 2), (1, 2)]
for i, (a, b) in enumerate(pairs):
    coef = svm.coef_[i].toarray().ravel()
    order = np.argsort(coef)
    print(f"\n{classes[a]} vs {classes[b]}")
    print(f"Condong ke {classes[a]}:", terms[order[-10:]][::-1])  
    print(f"Condong ke {classes[b]}:", terms[order[:10]])         