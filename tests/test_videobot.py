import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml

import drive_source
import rodar
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

    def test_prefere_pasta_sincronizada_sem_baixar(self):
        with tempfile.TemporaryDirectory() as pasta:
            raiz = Path(pasta)
            fonte = raiz / "Limpeza" / "video 01.mp4"
            fonte.parent.mkdir()
            fonte.write_bytes(b"video-teste")
            item, caminho = drive_source.escolher_e_baixar(
                "https://drive.google.com/drive/folders/1AbC_def-123",
                raiz / "downloads",
                raiz / "usados.txt",
                sync_root=str(raiz),
                folder_name="Limpeza",
            )
        self.assertEqual(caminho, fonte)
        self.assertTrue(item.id.startswith("local-"))

    def test_plano_social_cobre_todos_os_perfis(self):
        social = yaml.safe_load(
            (videobot.BASE / "config" / "contas.yml").read_text(encoding="utf-8")
        )["contas"]
        canais = videobot.carregar_config().canais
        self.assertEqual(set(social), {c.id for c in canais})
        handles = [x["handle"] for x in social.values()]
        self.assertEqual(len(handles), len(set(handles)))

    def test_tema_manual_gera_sem_mudar_configuracao_drive(self):
        canal = videobot.carregar_config().canais[0]
        self.assertEqual(canal.modo, "drive")
        with tempfile.TemporaryDirectory() as pasta:
            with mock.patch.object(videobot, "DADOS", Path(pasta)):
                with mock.patch.object(videobot, "ambiente_do_canal", return_value={
                    "VIDEOBOT_MODO": "drive", "CANAL": canal.id,
                }):
                    with mock.patch.object(videobot.subprocess, "run") as run:
                        run.return_value.returncode = 0
                        codigo = videobot.executar(
                            canal, teste=True, tema="Buraco negro",
                            termos="black hole space",
                        )
        self.assertEqual(codigo, 0)
        kwargs = run.call_args.kwargs
        self.assertEqual(kwargs["env"]["VIDEOBOT_MODO"], "gerar")
        self.assertEqual(kwargs["env"]["VIDEOBOT_TEMA"], "Buraco negro")
        self.assertEqual(kwargs["env"]["VIDEOBOT_TERMOS"], "black hole space")
        self.assertIn("--teste", run.call_args.args[0])
        self.assertEqual(canal.modo, "drive")

    def test_termos_sem_tema_sao_rejeitados(self):
        self.assertEqual(videobot.main([
            "rodar", "--canal", "memes", "--termos", "space",
        ]), 2)

    def test_tema_manual_pula_a_pauta_automatica(self):
        with mock.patch.object(rodar, "MODO", "gerar"), \
             mock.patch.object(rodar, "TESTE", True), \
             mock.patch.object(rodar, "TEMA_MANUAL", "Buraco negro"), \
             mock.patch.object(rodar, "TERMOS_MANUAIS", "black hole"), \
             mock.patch.object(rodar, "NICHOS_CANAL", ["tecnologia"]), \
             mock.patch.object(rodar, "atualizar_temas") as atualizar, \
             mock.patch.object(rodar, "proximo_tema") as proximo, \
             mock.patch.object(rodar, "escolher_fonte", return_value=("pexels", None)), \
             mock.patch.object(rodar, "gerar", return_value=("teste.mp4", "")) as gerar:
            rodar.main()
        atualizar.assert_not_called()
        proximo.assert_not_called()
        self.assertEqual(gerar.call_args.args[:2], ("Buraco negro", "black hole"))


if __name__ == "__main__":
    unittest.main()
