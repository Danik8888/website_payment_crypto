// ======================== MAIN SCRIPT ========================

// FAQ аккордеон
function toggleFaq(button) {
    const item = button.parentElement;
    const isActive = item.classList.contains('active');
    
    // Закрываем все
    document.querySelectorAll('.faq-item.active').forEach(el => {
        if (el !== item) {
            el.classList.remove('active');
        }
    });
    
    // Переключаем текущий
    if (isActive) {
        item.classList.remove('active');
    } else {
        item.classList.add('active');
    }
}

// Копирование текста в буфер обмена
function copyToClipboard(text, buttonElement) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => {
            showCopyFeedback(buttonElement);
        }).catch(() => {
            fallbackCopy(text, buttonElement);
        });
    } else {
        fallbackCopy(text, buttonElement);
    }
}

function fallbackCopy(text, buttonElement) {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
        document.execCommand('copy');
        showCopyFeedback(buttonElement);
    } catch (e) {
        console.error('Copy failed:', e);
    }
    document.body.removeChild(textarea);
}

function showCopyFeedback(buttonElement) {
    const originalText = buttonElement.textContent || buttonElement.innerText;
    buttonElement.textContent = '✅ Скопировано!';
    buttonElement.style.borderColor = '#22c55e';
    buttonElement.style.color = '#22c55e';
    
    setTimeout(() => {
        buttonElement.textContent = originalText;
        buttonElement.style.borderColor = '';
        buttonElement.style.color = '';
    }, 2000);
}

// Форматирование чисел
function formatNumber(num) {
    return new Intl.NumberFormat('ru-RU').format(num);
}

// Плавный скролл
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// Добавляем класс active для навигации
document.addEventListener('DOMContentLoaded', function() {
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        if (link.getAttribute('href') === currentPath) {
            link.style.color = 'var(--primary)';
            link.style.background = 'rgba(247, 147, 26, 0.1)';
        }
    });
});