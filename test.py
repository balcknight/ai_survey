from kmer_judge import classify_peaks
cases = [
    ([23,45,90,135,179],0.2),
    ([20,40,60],0.2),
    ([20,40,80],0.2),
    ([20,40,60,120],0.2),
    ([20,38,59],0.2),
]
for depths,tol in cases:
    pattern,is_normal,detail = classify_peaks(depths,tol)
    print(depths,'=>',pattern,is_normal,detail)