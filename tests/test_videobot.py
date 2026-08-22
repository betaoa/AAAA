import datetime as dt
import tempfile
import unittest
from pathlib import Path

import drive_source
import videobot

CONFIG = """\
versao: 1
padroes:
  fuso: America/Cuiaba
  tolerancia_minutos: 35
canais:
  - id: teste
    ativo: true
    nichos: [tecnologia]
    plataformas: [youtube, instagram]
    horarios: [\"09:05\"]
"""


class ConfigTests(unittest.TestCase):
    def test_carrega_configuracao(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "canais.yml"
            caminho.write_text(CONFIG, encoding="utf-8")
            config = videobot.carregar_config(caminho)
        self.assertEqual(config.canais[0].id, "teste")
        self.assertEqual(config.canais[0].plataformas, ("youtube", "instagram"))
        self.assertEqual(config.canais[0].modo, "gerar")

    def test_rejeita_horario_invalido(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "canais.yml"
            caminho.write_text(CONFIG.replace('"09:05"', '"25:99"'), encoding="utf-8")
            with self.assertRaises(videobot.ErroConfig):
                videobot.carregar_config(caminho)

    def test_slot_dentro_da_tolerancia(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "canais.yml"
            caminho.write_text(CONFIG, encoding="utf-8")
            config = videobot.carregar_config(caminho)
        canal = config.canais[0]
        agora = dt.datetime(2026, 8, 22, 13, 20, tzinfo=dt.timezone.utc)
        original = videobot._estado
        videobot._estado = lambda _canal: {"slots": {}}
        try:
            slot = videobot._slot_pendente(canal, config, agora)
        finally:
            videobot._estado = original
        self.assertEqual(slot, "2026-08-22@09:05@America/Cuiaba")

    def test_config_real_tem_31_nichos_e_cinco_horarios(self):
        config = videobot.carregar_config(videobot.CONFIG_PADRAO)
        self.assertEqual(len(config.canais), 31)
        self.assertTrue(all(len(c.horarios) == 5 for c in config.canais))
        self.assertTrue(all(c.modo == "drive" for c in config.canais))
        self.assertTrue(all(set(c.plataformas) == {"youtube", "instagram", "tiktok"}
                            for c in config.canais))
        self.assertEqual(sum(c.id == "family-guy" for c in config.canais), 1)

    def test_extrai_id_de_pasta_drive(self):
        url = "https://drive.google.com/drive/folders/1AbC_def-123?usp=sharing"
        self.assertEqual(drive_source.extrair_id(url), "1AbC_def-123")


if __name__ == "__main__":
    unittest.main()
