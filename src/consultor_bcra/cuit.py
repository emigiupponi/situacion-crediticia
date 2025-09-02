import re
def validar_cuit(cuit: str) -> bool:
    if not re.fullmatch(r"\d{11}", cuit or ""): return False
    nums = list(map(int, cuit)); coef = [5,4,3,2,7,6,5,4,3,2]
    dv = 11 - (sum(a*b for a,b in zip(coef, nums[:10])) % 11)
    dv = 0 if dv==11 else (9 if dv==10 else dv)
    return dv == nums[10]
