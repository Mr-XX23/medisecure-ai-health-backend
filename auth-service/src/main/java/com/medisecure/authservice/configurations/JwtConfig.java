package com.medisecure.authservice.configurations;

import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import com.nimbusds.jose.jwk.source.JWKSource;
import com.nimbusds.jose.proc.SecurityContext;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;

import java.io.InputStream;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

@Configuration
public class JwtConfig {

    @Value("${jwt.public-key:#{null}}")
    private Resource publicKeyResource;

    @Value("${jwt.private-key:#{null}}")
    private Resource privateKeyResource;


    /**
     * Generate RSA Key Pair
     */
    @Bean
    public KeyPair keyPair() {
        try {
            if (publicKeyResource != null && privateKeyResource != null && publicKeyResource.exists() && privateKeyResource.exists()) {
                RSAPublicKey publicKey = readPublicKey(publicKeyResource);
                RSAPrivateKey privateKey = readPrivateKey(privateKeyResource);

                return new KeyPair(publicKey, privateKey);
            }

            // Generate new key pair if files not found
            KeyPairGenerator keyPairGenerator = KeyPairGenerator.getInstance("RSA");
            keyPairGenerator.initialize(2048);
            return keyPairGenerator.generateKeyPair();
        } catch (Exception e) {
            throw new IllegalStateException("Unable to generate RSA key pair", e);
        }
    }

    /**
     * Read RSAPublic Key from file
     */
    private RSAPublicKey readPublicKey(Resource resource) throws Exception {
        try (InputStream is = resource.getInputStream()) {
            String key = new String(is.readAllBytes())
                    .replace("-----BEGIN PUBLIC KEY-----", "")
                    .replace("-----END PUBLIC KEY-----", "")
                    .replaceAll("\\s", "");

            byte[] keyBytes = Base64.getDecoder().decode(key);
            X509EncodedKeySpec spec = new X509EncodedKeySpec(keyBytes);
            KeyFactory keyFactory = KeyFactory.getInstance("RSA");
            return (RSAPublicKey) keyFactory.generatePublic(spec);
        }
    }

    /**
     * Read RSAPrivate Key from file
     */
    private RSAPrivateKey readPrivateKey(Resource resource) throws Exception {
        try (InputStream is = resource.getInputStream()) {
            String key = new String(is.readAllBytes())
                    .replace("-----BEGIN PRIVATE KEY-----", "")
                    .replace("-----END PRIVATE KEY-----", "")
                    .replaceAll("\\s", "");

            byte[] keyBytes = Base64.getDecoder().decode(key);
            PKCS8EncodedKeySpec spec = new PKCS8EncodedKeySpec(keyBytes);
            KeyFactory keyFactory = KeyFactory.getInstance("RSA");
            return (RSAPrivateKey) keyFactory.generatePrivate(spec);
        }
    }

    /**
     * Configure JWK Source
     */
    @Bean
    public JWKSource<SecurityContext> jwkSource() {
        KeyPair keyPair = keyPair();
        RSAPublicKey publicKey = (RSAPublicKey) keyPair.getPublic();
        RSAPrivateKey privateKey = (RSAPrivateKey) keyPair.getPrivate();

        JWK jwk = new RSAKey.Builder(publicKey)
                .privateKey(privateKey)
                .build();
        JWKSet jwkSet = new JWKSet(jwk);
        return new ImmutableJWKSet<>(jwkSet);
    }

    /**
     * Get the JwtEncoder and JwtDecoder beans
     */
    @Bean
    public JwtEncoder jwtEncoder() {
        return new NimbusJwtEncoder(jwkSource());
    }

    @Bean
    public JwtDecoder jwtDecoder() {
        KeyPair keyPair = keyPair();
        return NimbusJwtDecoder.withPublicKey((RSAPublicKey) keyPair.getPublic()).build();
    }
}
