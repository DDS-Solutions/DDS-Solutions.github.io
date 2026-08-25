// Modal Management
let lastFocusedElement = null;

function getFocusableElements(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )).filter(el => !el.hasAttribute('disabled') && el.offsetParent !== null);
}

function openModal(modalId) {
    const targetId = typeof modalId === 'string' ? modalId : 'featureModal';
    const modal = document.getElementById(targetId);
    if (!modal) return;

    lastFocusedElement = document.activeElement;
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';

    // Focus the close button or first focusable element
    const focusables = getFocusableElements(modal);
    if (focusables.length > 0) {
        focusables[0].focus();
    }
}

function closeModal(modalId) {
    const modals = modalId ? [document.getElementById(modalId)] : document.querySelectorAll('.modal');
    modals.forEach(modal => {
        if (modal && modal.style.display === 'flex') {
            modal.style.display = 'none';
        }
    });

    const anyOpen = Array.from(document.querySelectorAll('.modal')).some(m => m.style.display === 'flex');
    if (!anyOpen) {
        document.body.style.overflow = 'auto';
        if (lastFocusedElement && typeof lastFocusedElement.focus === 'function') {
            lastFocusedElement.focus();
            lastFocusedElement = null;
        }
    }
}

function openEcosystemModal() {
    openModal('ecosystemModal');
}

function closeEcosystemModal() {
    closeModal('ecosystemModal');
}

document.addEventListener('DOMContentLoaded', function () {
    // Wire Modal Open Buttons
    const openEcosystemBtn = document.getElementById('openEcosystemModalBtn');
    if (openEcosystemBtn) {
        openEcosystemBtn.addEventListener('click', function (e) {
            e.preventDefault();
            openEcosystemModal();
        });
    }

    const openFeatureBtn = document.getElementById('openFeatureModalBtn');
    if (openFeatureBtn) {
        openFeatureBtn.addEventListener('click', function (e) {
            e.preventDefault();
            openModal('featureModal');
        });
    }

    // Generic data-modal-target buttons
    document.querySelectorAll('[data-modal-target]').forEach(trigger => {
        trigger.addEventListener('click', function (e) {
            e.preventDefault();
            const targetId = trigger.getAttribute('data-modal-target');
            if (targetId) openModal(targetId);
        });
    });

    // Modal Close Buttons
    const closeFeatureBtn = document.getElementById('closeFeatureModalBtn');
    if (closeFeatureBtn) {
        closeFeatureBtn.addEventListener('click', () => closeModal('featureModal'));
    }

    const closeEcosystemBtn = document.getElementById('closeEcosystemModalBtn');
    if (closeEcosystemBtn) {
        closeEcosystemBtn.addEventListener('click', () => closeModal('ecosystemModal'));
    }

    document.querySelectorAll('.modal .close-btn').forEach(btn => {
        btn.addEventListener('click', function () {
            const parentModal = btn.closest('.modal');
            if (parentModal) closeModal(parentModal.id);
        });
    });

    // Close on outside backdrop click
    window.addEventListener('click', function (event) {
        if (event.target && event.target.classList && event.target.classList.contains('modal')) {
            closeModal(event.target.id);
        }
    });

    // Modal Keyboard Trap & Escape handling
    document.addEventListener('keydown', function (e) {
        const activeModal = Array.from(document.querySelectorAll('.modal')).find(m => m.style.display === 'flex');

        if (e.key === 'Escape' && activeModal) {
            closeModal(activeModal.id);
            return;
        }

        if (e.key === 'Tab' && activeModal) {
            const focusables = getFocusableElements(activeModal);
            if (focusables.length === 0) {
                e.preventDefault();
                return;
            }
            const first = focusables[0];
            const last = focusables[focusables.length - 1];

            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
        }
    });

    // Screenshot Carousel Logic
    const carouselWrapper = document.querySelector('.carousel-wrapper') || document.getElementById('carouselTrack')?.parentElement;
    const track = document.getElementById('carouselTrack');
    const dotsContainer = document.getElementById('carouselDots');
    const slides = track ? track.querySelectorAll('.carousel-slide') : [];
    const prevBtn = document.querySelector('.carousel-nav.prev');
    const nextBtn = document.querySelector('.carousel-nav.next');

    if (track && slides.length > 0) {
        // Create dot indicators if dotsContainer exists
        if (dotsContainer) {
            dotsContainer.innerHTML = '';
            slides.forEach((_, index) => {
                const dot = document.createElement('button');
                dot.type = 'button';
                dot.className = 'carousel-dot' + (index === 0 ? ' active' : '');
                dot.setAttribute('aria-label', `Go to slide ${index + 1}`);
                dot.addEventListener('click', () => scrollToSlide(index));
                dotsContainer.appendChild(dot);
            });
        }

        const dots = dotsContainer ? dotsContainer.querySelectorAll('.carousel-dot') : [];

        // Scroll to specific slide
        function scrollToSlide(index) {
            const slide = slides[index];
            if (slide) {
                const trackRect = track.getBoundingClientRect();
                const slideRect = slide.getBoundingClientRect();
                const scrollPos = track.scrollLeft + slideRect.left - trackRect.left - (trackRect.width - slideRect.width) / 2;
                track.scrollTo({ left: scrollPos, behavior: 'smooth' });
            }
        }

        // Update active dot on scroll with rAF throttle
        let isScrolling = false;
        function updateActiveDot() {
            if (dots.length === 0) return;
            const trackCenter = track.scrollLeft + track.clientWidth / 2;
            let closestIndex = 0;
            let closestDistance = Infinity;

            slides.forEach((slide, index) => {
                const slideCenter = slide.offsetLeft + slide.offsetWidth / 2;
                const distance = Math.abs(trackCenter - slideCenter);
                if (distance < closestDistance) {
                    closestDistance = distance;
                    closestIndex = index;
                }
            });

            dots.forEach((dot, index) => {
                dot.classList.toggle('active', index === closestIndex);
            });
            isScrolling = false;
        }

        track.addEventListener('scroll', function () {
            if (!isScrolling) {
                window.requestAnimationFrame(updateActiveDot);
                isScrolling = true;
            }
        }, { passive: true });

        // Arrow button navigation
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                track.scrollBy({ left: -300, behavior: 'smooth' });
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                track.scrollBy({ left: 300, behavior: 'smooth' });
            });
        }

        // Keyboard navigation scoped to carousel focus / hover
        const isCarouselFocusedOrHovered = () => {
            if (!carouselWrapper && !track) return false;
            const active = document.activeElement;
            const hasFocus = (track && track.contains(active)) ||
                (carouselWrapper && carouselWrapper.contains(active)) ||
                (dotsContainer && dotsContainer.contains(active));
            const isHovered = (carouselWrapper && carouselWrapper.matches(':hover')) ||
                (track && track.matches(':hover'));
            return hasFocus || isHovered;
        };

        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft' && isCarouselFocusedOrHovered()) {
                track.scrollBy({ left: -300, behavior: 'smooth' });
            } else if (e.key === 'ArrowRight' && isCarouselFocusedOrHovered()) {
                track.scrollBy({ left: 300, behavior: 'smooth' });
            }
        });
    }

    // Scroll Reveal Animation (IntersectionObserver)
    const revealElements = document.querySelectorAll('.reveal');

    if (revealElements.length > 0) {
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        if (prefersReducedMotion) {
            revealElements.forEach(el => {
                el.style.opacity = '1';
                el.style.transform = 'none';
            });
        } else {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('revealed');
                        observer.unobserve(entry.target);
                    }
                });
            }, {
                threshold: 0.15,
                rootMargin: '0px 0px -50px 0px'
            });

            revealElements.forEach(el => observer.observe(el));
        }
    }

    // Initialize Medium Zoom
    if (typeof mediumZoom === 'function') {
        mediumZoom('.carousel-slide img:not(.no-zoom)', {
            margin: 0,
            background: '#100b20',
            scrollOffset: 0,
        });
    } else {
        console.warn('Medium Zoom library not loaded.');
    }
});
