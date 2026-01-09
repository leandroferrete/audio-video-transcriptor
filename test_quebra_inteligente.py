#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Teste da função de quebra inteligente de legendas
"""

import sys
from pathlib import Path

# Adiciona o diretório ao path
sys.path.insert(0, str(Path(__file__).parent))

from transcribe_pro_karaoke_docker import Word, smart_split_by_words_and_timing, should_split_segment


def test_quebra_inteligente():
    """Testa a quebra de uma frase longa problemática"""
    
    # Simula o texto problemático: "A EMI É A MARGEM INTEGRADA, ENTÃO ASSIM..."
    texto_completo = """A EMI É A MARGEM INTEGRADA, ENTÃO ASSIM, É O PERCENTUAL 
DE MARGEM QUE A ALI VAI GANHAR EM CIMA DO PREÇO QUE ESTÁ ENTRE AQUELE PREÇO FOB""".replace('\n', ' ')
    
    palavras = texto_completo.split()
    
    # Simula timestamps (0.3s por palavra em média)
    words = []
    current_time = 21.631
    for i, palavra in enumerate(palavras):
        start = current_time
        end = current_time + 0.3
        words.append(Word(start=start, end=end, text=palavra))
        current_time = end + 0.1  # gap de 100ms
    
    print("=" * 70)
    print("🔍 TESTE DE QUEBRA INTELIGENTE")
    print("=" * 70)
    print()
    
    # Info original
    total_palavras = len(words)
    total_chars = sum(len(w.text) for w in words) + len(words) - 1
    duracao = words[-1].end - words[0].start
    
    print(f"📊 SEGMENTO ORIGINAL:")
    print(f"   Palavras: {total_palavras}")
    print(f"   Caracteres: {total_chars}")
    print(f"   Duração: {duracao:.1f}s")
    print(f"   Texto: {' '.join(w.text for w in words)}")
    print()
    
    # Testa se deve quebrar
    deve_quebrar = should_split_segment(words, max_chars_total=84, max_duration=6.0)
    print(f"❓ Deve quebrar? {'✅ SIM' if deve_quebrar else '❌ NÃO'}")
    print()
    
    # Quebra inteligente
    if deve_quebrar:
        subsegmentos = smart_split_by_words_and_timing(
            words,
            max_words_per_line=9,
            max_words_total=14,
            min_pause_for_break=0.25,
            max_chars_per_segment=84
        )
        
        print(f"🎯 RESULTADO: {len(subsegmentos)} subsegmentos criados")
        print("=" * 70)
        print()
        
        for idx, subseg in enumerate(subsegmentos, 1):
            sub_palavras = len(subseg)
            sub_chars = sum(len(w.text) for w in subseg) + len(subseg) - 1
            sub_duracao = subseg[-1].end - subseg[0].start
            sub_texto = ' '.join(w.text for w in subseg)
            
            print(f"📝 SUBSEGMENTO {idx}:")
            print(f"   Palavras: {sub_palavras} {'✅' if sub_palavras <= 14 else '❌'}")
            print(f"   Caracteres: {sub_chars} {'✅' if sub_chars <= 84 else '❌'}")
            print(f"   Duração: {sub_duracao:.1f}s")
            print(f"   Texto: {sub_texto}")
            print()
    
    print("=" * 70)
    print("✅ TESTE CONCLUÍDO!")
    print("=" * 70)


if __name__ == "__main__":
    test_quebra_inteligente()
