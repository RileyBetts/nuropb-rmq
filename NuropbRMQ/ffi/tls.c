/* Copyright © 2026, Riley Betts Ltd (rileybetts.ai)
 * Released under Apache 2.0 license as described in the file LICENSE.
 *
 * Optional OpenSSL AMQPS (tls-verify-full). Not linked by defaultTargets.
 */
#include <lean/lean.h>
#include <openssl/ssl.h>
#include <openssl/err.h>
#include <openssl/pem.h>
#include <openssl/pkcs12.h>
#include <openssl/provider.h>
#include <openssl/x509.h>
#include <openssl/evp.h>
#include <openssl/ecdsa.h>
#include <openssl/bn.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdio.h>

static lean_obj_res io_error(const char *msg) {
  return lean_io_result_mk_error(lean_mk_io_user_error(lean_mk_string(msg)));
}

static lean_obj_res io_error_ssl(const char *msg) {
  unsigned long err = ERR_get_error();
  char buf[256];
  if (err == 0) return io_error(msg);
  ERR_error_string_n(err, buf, sizeof(buf));
  char out[384];
  snprintf(out, sizeof(out), "%s: %s", msg, buf);
  return io_error(out);
}

typedef struct {
  SSL_CTX *ctx;
  SSL *ssl;
  int fd;
} NuropbTls;

static void ensure_ssl(void) {
  static int once = 0;
  if (!once) {
    OPENSSL_init_ssl(0, NULL);
    OPENSSL_init_crypto(OPENSSL_INIT_LOAD_CONFIG, NULL);
    (void)OSSL_PROVIDER_load(NULL, "default");
    SSL_load_error_strings();
    OpenSSL_add_ssl_algorithms();
    once = 1;
  }
}

static lean_obj_res finish_ssl(SSL_CTX *ctx, uint32_t fd, const char *hn) {
  SSL *ssl = SSL_new(ctx);
  if (!ssl) {
    SSL_CTX_free(ctx);
    return io_error("SSL_new failed");
  }
  SSL_set_fd(ssl, (int)fd);
  if (hn[0] != '\0') {
    SSL_set_tlsext_host_name(ssl, hn);
    SSL_set1_host(ssl, hn);
  }
  if (SSL_connect(ssl) != 1) {
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    return io_error("SSL_connect failed (tls-verify-full)");
  }
  NuropbTls *sess = (NuropbTls *)malloc(sizeof(NuropbTls));
  if (!sess) {
    SSL_free(ssl);
    SSL_CTX_free(ctx);
    return io_error("oom");
  }
  sess->ctx = ctx;
  sess->ssl = ssl;
  sess->fd = (int)fd;
  return lean_io_result_mk_ok(lean_box_uint64((uint64_t)(uintptr_t)sess));
}

LEAN_EXPORT lean_obj_res nuropb_tls_connect(
    uint32_t fd,
    b_lean_obj_arg hostname,
    b_lean_obj_arg ca_pem,
    b_lean_obj_arg cert_pem,
    b_lean_obj_arg key_pem,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  const SSL_METHOD *method = TLS_client_method();
  SSL_CTX *ctx = SSL_CTX_new(method);
  if (!ctx) return io_error("SSL_CTX_new failed");
  SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
  const char *ca = lean_string_cstr(ca_pem);
  if (ca[0] != '\0') {
    BIO *bio = BIO_new_mem_buf(ca, -1);
    X509 *cert = PEM_read_bio_X509(bio, NULL, 0, NULL);
    BIO_free(bio);
    if (!cert) {
      SSL_CTX_free(ctx);
      return io_error("failed to parse CA PEM");
    }
    X509_STORE *store = SSL_CTX_get_cert_store(ctx);
    X509_STORE_add_cert(store, cert);
    X509_free(cert);
  } else {
    SSL_CTX_set_default_verify_paths(ctx);
  }
  const char *cert = lean_string_cstr(cert_pem);
  const char *key = lean_string_cstr(key_pem);
  if (cert[0] != '\0' && key[0] != '\0') {
    BIO *cbio = BIO_new_mem_buf(cert, -1);
    X509 *xc = PEM_read_bio_X509(cbio, NULL, 0, NULL);
    BIO_free(cbio);
    BIO *kbio = BIO_new_mem_buf(key, -1);
    EVP_PKEY *pk = PEM_read_bio_PrivateKey(kbio, NULL, 0, NULL);
    BIO_free(kbio);
    if (!xc || !pk || SSL_CTX_use_certificate(ctx, xc) != 1 ||
        SSL_CTX_use_PrivateKey(ctx, pk) != 1) {
      if (xc) X509_free(xc);
      if (pk) EVP_PKEY_free(pk);
      SSL_CTX_free(ctx);
      return io_error("failed to load client cert/key");
    }
    X509_free(xc);
    EVP_PKEY_free(pk);
  }
  return finish_ssl(ctx, fd, lean_string_cstr(hostname));
}

LEAN_EXPORT lean_obj_res nuropb_tls_connect_pkcs12(
    uint32_t fd,
    b_lean_obj_arg hostname,
    b_lean_obj_arg ca_pem,
    b_lean_obj_arg p12_path,
    b_lean_obj_arg password,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  const SSL_METHOD *method = TLS_client_method();
  SSL_CTX *ctx = SSL_CTX_new(method);
  if (!ctx) return io_error("SSL_CTX_new failed");
  SSL_CTX_set_verify(ctx, SSL_VERIFY_PEER, NULL);
  const char *ca = lean_string_cstr(ca_pem);
  if (ca[0] != '\0') {
    BIO *bio = BIO_new_mem_buf(ca, -1);
    X509 *cert = PEM_read_bio_X509(bio, NULL, 0, NULL);
    BIO_free(bio);
    if (!cert) {
      SSL_CTX_free(ctx);
      return io_error("failed to parse CA PEM");
    }
    X509_STORE *store = SSL_CTX_get_cert_store(ctx);
    X509_STORE_add_cert(store, cert);
    X509_free(cert);
  } else {
    SSL_CTX_set_default_verify_paths(ctx);
  }
  FILE *fp = fopen(lean_string_cstr(p12_path), "rb");
  if (!fp) {
    SSL_CTX_free(ctx);
    return io_error("failed to open PKCS#12 file");
  }
  PKCS12 *p12 = d2i_PKCS12_fp(fp, NULL);
  fclose(fp);
  if (!p12) {
    SSL_CTX_free(ctx);
    return io_error("failed to parse PKCS#12");
  }
  EVP_PKEY *pk = NULL;
  X509 *xc = NULL;
  STACK_OF(X509) *ca_stack = NULL;
  size_t plen = lean_string_size(password);
  char passbuf[256];
  if (plen >= sizeof(passbuf)) {
    PKCS12_free(p12);
    SSL_CTX_free(ctx);
    return io_error("PKCS#12 password too long");
  }
  memcpy(passbuf, lean_string_cstr(password), plen);
  passbuf[plen] = '\0';
  if (PKCS12_parse(p12, plen == 0 ? NULL : passbuf, &pk, &xc, &ca_stack) != 1 ||
      !xc || !pk) {
    PKCS12_free(p12);
    if (pk) EVP_PKEY_free(pk);
    if (xc) X509_free(xc);
    if (ca_stack) sk_X509_pop_free(ca_stack, X509_free);
    SSL_CTX_free(ctx);
    return io_error_ssl("failed to load PKCS#12 client cert/key");
  }
  PKCS12_free(p12);
  if (SSL_CTX_use_certificate(ctx, xc) != 1 || SSL_CTX_use_PrivateKey(ctx, pk) != 1) {
    EVP_PKEY_free(pk);
    X509_free(xc);
    if (ca_stack) sk_X509_pop_free(ca_stack, X509_free);
    SSL_CTX_free(ctx);
    return io_error("failed to install PKCS#12 client cert/key");
  }
  X509_free(xc);
  EVP_PKEY_free(pk);
  if (ca_stack) {
    X509_STORE *store = SSL_CTX_get_cert_store(ctx);
    for (int i = 0; i < sk_X509_num(ca_stack); i++) {
      X509 *extra = sk_X509_value(ca_stack, i);
      if (extra) X509_STORE_add_cert(store, extra);
    }
    sk_X509_pop_free(ca_stack, X509_free);
  }
  return finish_ssl(ctx, fd, lean_string_cstr(hostname));
}

LEAN_EXPORT lean_obj_res nuropb_tls_send(uint64_t handle, b_lean_obj_arg buf, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  size_t n = lean_sarray_size(buf);
  uint8_t *data = lean_sarray_cptr(buf);
  size_t sent = 0;
  while (sent < n) {
    int r = SSL_write(sess->ssl, data + sent, (int)(n - sent));
    if (r <= 0) return io_error("SSL_write failed");
    sent += (size_t)r;
  }
  return lean_io_result_mk_ok(lean_box(0));
}

LEAN_EXPORT lean_obj_res nuropb_tls_pending(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (!sess || !sess->ssl) return lean_io_result_mk_ok(lean_box(0));
  int n = SSL_pending(sess->ssl);
  return lean_io_result_mk_ok(lean_box(n > 0 ? 1 : 0));
}

LEAN_EXPORT lean_obj_res nuropb_tls_recv(uint64_t handle, uint32_t max, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (max == 0) max = 4096;
  lean_object *arr = lean_alloc_sarray(1, 0, max);
  uint8_t *dst = lean_sarray_cptr(arr);
  int r = SSL_read(sess->ssl, dst, (int)max);
  if (r <= 0) {
    lean_dec(arr);
    return io_error("SSL_read failed");
  }
  lean_sarray_set_size(arr, (size_t)r);
  return lean_io_result_mk_ok(arr);
}

LEAN_EXPORT lean_obj_res nuropb_tls_close(uint64_t handle, lean_obj_arg w) {
  (void)w;
  NuropbTls *sess = (NuropbTls *)(uintptr_t)handle;
  if (sess) {
    SSL_shutdown(sess->ssl);
    SSL_free(sess->ssl);
    SSL_CTX_free(sess->ctx);
    free(sess);
  }
  return lean_io_result_mk_ok(lean_box(0));
}

static char *dup_lean_string(b_lean_obj_arg s) {
  size_t n = lean_string_size(s);
  char *p = (char *)malloc(n == 0 ? 1 : n);
  if (!p) return NULL;
  if (n == 0) {
    p[0] = '\0';
    return p;
  }
  memcpy(p, lean_string_cstr(s), n);
  return p;
}

static int ecdsa_p1363_to_der(const unsigned char *raw, size_t rawlen,
                              unsigned char **out, size_t *outlen) {
  if (rawlen == 0 || (rawlen % 2) != 0) return 0;
  size_t half = rawlen / 2;
  ECDSA_SIG *esig = ECDSA_SIG_new();
  if (!esig) return 0;
  BIGNUM *r = BN_bin2bn(raw, (int)half, NULL);
  BIGNUM *s = BN_bin2bn(raw + half, (int)half, NULL);
  if (!r || !s || ECDSA_SIG_set0(esig, r, s) != 1) {
    BN_free(r);
    BN_free(s);
    ECDSA_SIG_free(esig);
    return 0;
  }
  int len = i2d_ECDSA_SIG(esig, NULL);
  if (len <= 0) {
    ECDSA_SIG_free(esig);
    return 0;
  }
  *out = (unsigned char *)malloc((size_t)len);
  if (!*out) {
    ECDSA_SIG_free(esig);
    return 0;
  }
  unsigned char *p = *out;
  i2d_ECDSA_SIG(esig, &p);
  *outlen = (size_t)len;
  ECDSA_SIG_free(esig);
  return 1;
}

/* RS256 / ES256 JWS verify. Returns IO Bool (false = fail-closed). */
LEAN_EXPORT lean_obj_res nuropb_jwt_verify_asymmetric(
    b_lean_obj_arg alg,
    b_lean_obj_arg pem_pub,
    b_lean_obj_arg signing,
    b_lean_obj_arg sig,
    lean_obj_arg w) {
  (void)w;
  ensure_ssl();
  char *alg_s = dup_lean_string(alg);
  char *pem = dup_lean_string(pem_pub);
  char *msg = dup_lean_string(signing);
  if (!alg_s || !pem || !msg) {
    free(alg_s);
    free(pem);
    free(msg);
    return io_error("oom");
  }
  size_t msg_len = strlen(msg);
  size_t sig_len = lean_sarray_size(sig);
  const unsigned char *sig_raw = lean_sarray_cptr(sig);
  int ok = 0;
  if (pem[0] == '\0' || msg_len == 0 || sig_len == 0) {
    goto done;
  }
  BIO *bio = BIO_new_mem_buf(pem, -1);
  if (!bio) goto done;
  EVP_PKEY *pkey = PEM_read_bio_PUBKEY(bio, NULL, NULL, NULL);
  BIO_free(bio);
  if (!pkey) goto done;
  const unsigned char *use_sig = sig_raw;
  unsigned char *der = NULL;
  size_t use_len = sig_len;
  if (strcmp(alg_s, "ES256") == 0) {
    if (!ecdsa_p1363_to_der(sig_raw, sig_len, &der, &use_len)) {
      EVP_PKEY_free(pkey);
      goto done;
    }
    use_sig = der;
  } else if (strcmp(alg_s, "RS256") != 0) {
    EVP_PKEY_free(pkey);
    goto done;
  }
  EVP_MD_CTX *ctx = EVP_MD_CTX_new();
  if (ctx &&
      EVP_DigestVerifyInit(ctx, NULL, EVP_sha256(), NULL, pkey) == 1 &&
      EVP_DigestVerify(ctx, use_sig, use_len, (const unsigned char *)msg, msg_len) == 1) {
    ok = 1;
  }
  if (ctx) EVP_MD_CTX_free(ctx);
  EVP_PKEY_free(pkey);
  free(der);
done:
  free(alg_s);
  free(pem);
  free(msg);
  return lean_io_result_mk_ok(lean_box(ok ? 1 : 0));
}
