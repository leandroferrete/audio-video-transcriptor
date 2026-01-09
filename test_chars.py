"""Teste de cálculos de max_chars para legendas."""

def calc_max_chars(w, h, font_size, is_caps=True):
    is_vertical = h > w
    margin_l = 100
    margin_r = 100
    safety_factor = 0.75
    
    if is_vertical:
        usable_width = w * 0.60
        usable_width -= (margin_l + margin_r)
        char_width_estimate = font_size * (0.70 if is_caps else 0.58)
    else:
        usable_width = w * 0.75
        usable_width -= (margin_l + margin_r)
        char_width_estimate = font_size * (0.65 if is_caps else 0.55)
    
    usable_width *= safety_factor
    calculated = int(usable_width / char_width_estimate)
    
    if is_vertical:
        if w <= 720:
            max_chars = 12 if font_size >= 50 else 15
        elif w <= 1080:
            max_chars = 14 if font_size >= 50 else 18
        else:
            max_chars = 18 if font_size >= 50 else 22
    else:
        if w <= 1280:
            max_chars = 28 if font_size >= 50 else 32
        elif w <= 1920:
            max_chars = 32 if font_size >= 50 else 38
        else:
            max_chars = 38 if font_size >= 50 else 45
    
    final = min(calculated, max_chars)
    return final, calculated, usable_width

print('='*60)
print('TESTE DE MAX_CHARS (muito conservador)')
print('='*60)

configs = [
    ((1080, 1920), 52, 'Mobile 1080x1920, 52px'),
    ((1080, 1920), 46, 'Mobile 1080x1920, 46px'),
    ((1080, 1920), 38, 'Mobile 1080x1920, 38px'),
    ((720, 1280), 46, 'Mobile 720x1280, 46px'),
    ((1920, 1080), 52, 'Desktop 1920x1080, 52px'),
    ((1920, 1080), 46, 'Desktop 1920x1080, 46px'),
]

for (w, h), fs, nome in configs:
    final, calc, width = calc_max_chars(w, h, fs)
    is_vertical = h > w
    char_w = fs * 0.70
    est_text_width = final * char_w
    print(f'{nome}:')
    print(f'  Max chars: {final} (calc: {calc})')
    print(f'  Usable width: {width:.0f}px')
    print(f'  Est text width: {est_text_width:.0f}px')
    print(f'  Margem livre: {width - est_text_width:.0f}px')
    print()

# Exemplo visual
print('='*60)
print('EXEMPLO VISUAL - Texto que cabe em cada config:')
print('='*60)
texto = "A EMI É A MARGEM INTEGRADA QUE A EMPRESA"

for (w, h), fs, nome in configs:
    final, _, _ = calc_max_chars(w, h, fs)
    texto_cortado = texto[:final]
    print(f'{nome}: max={final}')
    print(f'  "{texto_cortado}"')
    print()
