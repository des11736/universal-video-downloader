"""动态自签 CA 根证书与叶子证书生成。

视频号下载需要 MITM 解密 ``channels.weixin.qq.com`` 的 HTTPS 流量,因此需要
一个本地可信的根 CA,并为目标域名签发叶子证书。本模块负责:

1. :func:`ensure_ca_cert`:首次运行时生成自签 CA 根证书(``ca.crt`` / ``ca.key``),
   已存在则直接复用。
2. :func:`sign_domain_cert`:用 CA 为指定域名签发带 SAN 的叶子证书。

依赖 ``cryptography`` 库(随 mitmproxy 间接安装)。若环境中缺失,会在导入时
给出清晰的安装提示。
"""

from __future__ import annotations

import datetime
import ipaddress
from pathlib import Path

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
except ImportError as exc:  # pragma: no cover - 依赖缺失提示
    raise ImportError(
        "未找到 cryptography 库,请执行 `pip install cryptography` 安装。"
        " 该库是 mitmproxy 的间接依赖,通常应已随项目安装。"
    ) from exc


def ensure_ca_cert(cert_dir: Path) -> tuple[Path, Path]:
    """确保证书目录中存在 CA 根证书与私钥。

    若 ``ca.crt`` 与 ``ca.key`` 都已存在,直接返回其路径;否则生成新的
    RSA 2048 自签根证书(CN="UVD Local CA",有效期 10 年)并写入 PEM 文件。

    Args:
        cert_dir: 证书存放目录,不存在时自动创建。

    Returns:
        ``(cert_path, key_path)`` 元组,分别为 CA 证书与私钥路径。
    """
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)

    cert_path = cert_dir / "ca.crt"
    key_path = cert_dir / "ca.key"

    # 已存在则直接复用,避免每次运行都重新生成导致系统信任失效
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path

    # 生成 RSA 2048 私钥
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # 证书主题与颁发者均为本 CA(自签)
    subject = issuer = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "UVD"),
            x509.NameAttribute(NameOID.COMMON_NAME, "UVD Local CA"),
        ]
    )

    now = datetime.datetime.utcnow()
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 年
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,  # CA 需要签发其他证书
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
    )

    certificate = builder.sign(private_key, hashes.SHA256())

    # 写入 PEM 文件
    cert_path.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )
    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return cert_path, key_path


def sign_domain_cert(
    domain: str, ca_cert: Path, ca_key: Path, out_dir: Path
) -> tuple[Path, Path]:
    """用 CA 为指定域名签发叶子证书。

    叶子证书包含 SAN(Subject Alternative Name),现代浏览器要求 SAN 而非 CN。
    若 ``domain`` 是 IP 地址,则加入 IP SAN。

    Args:
        domain: 目标域名或 IP(如 ``channels.weixin.qq.com``)。
        ca_cert: CA 证书路径。
        ca_key: CA 私钥路径。
        out_dir: 叶子证书输出目录。

    Returns:
        ``(leaf_cert_path, leaf_key_path)`` 元组。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 安全的文件名:替换域名中不允许出现在文件名的字符
    safe_name = domain.replace("*.", "").replace("/", "_").replace("\\", "_")
    leaf_cert_path = out_dir / f"{safe_name}.crt"
    leaf_key_path = out_dir / f"{safe_name}.key"

    # 读取 CA 证书与私钥
    ca_certificate = x509.load_pem_x509_certificate(ca_cert.read_bytes())
    ca_private_key = serialization.load_pem_private_key(
        ca_key.read_bytes(), password=None
    )

    # 生成叶子证书私钥
    leaf_private_key = rsa.generate_private_key(
        public_exponent=65537, key_size=2048
    )

    # 构建 SAN:域名用 DNS,IP 用 IPAddress
    san_list: list[x509.GeneralName] = []
    try:
        ip = ipaddress.ip_address(domain)
        san_list.append(x509.IPAddress(ip))
    except ValueError:
        # 不是 IP 则按域名处理,同时加入裸域名与通配符
        san_list.append(x509.DNSName(domain))
        if not domain.startswith("*."):
            san_list.append(x509.DNSName("*." + domain))

    subject = x509.Name(
        [
            x509.NameAttribute(NameOID.COUNTRY_NAME, "CN"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "UVD"),
            x509.NameAttribute(NameOID.COMMON_NAME, domain),
        ]
    )

    now = datetime.datetime.utcnow()
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_certificate.subject)
        .public_key(leaf_private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=825))  # 约 2 年
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None), critical=True
        )
        .add_extension(
            x509.SubjectAlternativeName(san_list), critical=False
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
    )

    certificate = builder.sign(ca_private_key, hashes.SHA256())

    leaf_cert_path.write_bytes(
        certificate.public_bytes(serialization.Encoding.PEM)
    )
    leaf_key_path.write_bytes(
        leaf_private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    return leaf_cert_path, leaf_key_path
