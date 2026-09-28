// ======================== PAYMENT PAGE SCRIPT ========================

let autoCheckInterval = null;
let isChecking = false;

// Копирование BTC адреса
function copyAddress() {
    const address = document.getElementById('btcAddress');
    if (address) {
        copyToClipboard(address.textContent.trim(), document.getElementById('copyBtn'));
    }
}

// Проверка оплаты
async function checkPayment() {
    if (isChecking) return;
    isChecking = true;

    const checkBtn = document.getElementById('checkBtn');
    const result = document.getElementById('paymentResult');
    const spinner = document.getElementById('paymentSpinner');
    const success = document.getElementById('paymentSuccess');
    const pending = document.getElementById('paymentPending');
    const error = document.getElementById('paymentError');

    // Показываем результат, скрываем всё кроме спиннера
    result.style.display = 'block';
    spinner.style.display = 'block';
    success.style.display = 'none';
    pending.style.display = 'none';
    error.style.display = 'none';
    
    if (checkBtn) checkBtn.disabled = true;

    try {
        const response = await fetch('/check-payment', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: `order_id=${encodeURIComponent(ORDER_ID)}`
        });

        const data = await response.json();
        spinner.style.display = 'none';

        if (data.success && data.paid) {
            // Оплата получена!
            success.style.display = 'block';
            if (checkBtn) checkBtn.style.display = 'none';
            
            // Останавливаем автопроверку
            stopAutoCheck();
            
            // Через 3 секунды переходим на страницу успеха
            setTimeout(() => {
                window.location.href = `/success/${ORDER_ID}`;
            }, 3000);
            
        } else if (data.success && !data.paid) {
            // Оплата еще не поступила
            pending.style.display = 'block';
            
            const receivedEl = document.getElementById('receivedAmount');
            if (receivedEl) {
                receivedEl.textContent = formatNumber(data.received_sats || 0);
            }
            
            if (checkBtn) checkBtn.disabled = false;
            
        } else {
            // Ошибка
            error.style.display = 'block';
            const errorMsg = document.getElementById('errorMessage');
            if (errorMsg) {
                errorMsg.textContent = data.message || 'Произошла ошибка при проверке оплаты';
            }
            if (checkBtn) checkBtn.disabled = false;
        }
    } catch (err) {
        spinner.style.display = 'none';
        error.style.display = 'block';
        const errorMsg = document.getElementById('errorMessage');
        if (errorMsg) {
            errorMsg.textContent = 'Ошибка соединения с сервером. Попробуйте позже.';
        }
        if (checkBtn) checkBtn.disabled = false;
        console.error('Check payment error:', err);
    }

    isChecking = false;
}

// Автоматическая проверка каждые 30 секунд
function startAutoCheck() {
    // Проверяем сразу
    setTimeout(checkPayment, 2000);
    
    // И потом каждые 30 секунд
    autoCheckInterval = setInterval(checkPayment, 30000);
}

function stopAutoCheck() {
    if (autoCheckInterval) {
        clearInterval(autoCheckInterval);
        autoCheckInterval = null;
    }
}

// Запускаем автопроверку при загрузке страницы
document.addEventListener('DOMContentLoaded', function() {
    startAutoCheck();
    
    // Останавливаем автопроверку, если пользователь уходит со страницы
    window.addEventListener('beforeunload', stopAutoCheck);
});