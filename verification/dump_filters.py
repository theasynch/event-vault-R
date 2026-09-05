import pywt

wavelets = ['haar', 'db4', 'bior4.4']

for w_name in wavelets:
    w = pywt.Wavelet(w_name)
    print(f"Wavelet: {w_name}")
    print(f"  dec_lo = {w.dec_lo}")
    print(f"  dec_hi = {w.dec_hi}")
    print(f"  rec_lo = {w.rec_lo}")
    print(f"  rec_hi = {w.rec_hi}")
    print()
