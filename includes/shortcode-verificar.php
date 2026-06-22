<?php
/**
 * Shortcode [et_verificar] — renderiza a página de verificação de autenticidade.
 * Uso: adicionar require_once em functions.php do tema:
 *   require_once get_template_directory() . '/../includes/shortcode-verificar.php';
 */
function et_verificar_shortcode() {
    ob_start();
    include plugin_dir_path(__FILE__) . '../assets/verificar.html';
    return ob_get_clean();
}
add_shortcode('et_verificar', 'et_verificar_shortcode');
