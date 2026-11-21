"""Faz o HTTPS deste projeto usar os certificados do Windows.

O Avast intercepta as conexões e apresenta um certificado assinado por uma
autoridade que o Windows confia, mas que não está na lista padrão do Python.
Sem este ajuste, o OpenSSL aborta ou recusa a conexão.
"""

import os

if os.name == "nt":
    # O Avast também injeta SSLKEYLOGFILE. No Python instalado pelo uv isso
    # encerra o processo com "no OPENSSL_Applink" na primeira conexão.
    os.environ.pop("SSLKEYLOGFILE", None)

    import truststore

    truststore.inject_into_ssl()
