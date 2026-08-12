
// Modal Logic
function openModal() {
    const modal = document.getElementById('featureModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden'; // Prevent scroll
    }
}

function closeModal() {
    const modal = document.getElementById('featureModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto'; // Restore scroll
    }
}

function openEcosystemModal() {
    const modal = document.getElementById('ecosystemModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function closeEcosystemModal() {
    const modal = document.getElementById('ecosystemModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

document.addEventListener('DOMContentLoaded', function () {
    // Modal Event Listeners
    const openEcosystemBtn = document.getElementById('openEcosystemModalBtn');
    if (openEcosystemBtn) {
        openEcosystemBtn.addEventListener('click', function (e) {
            e.preventDefault();
            openEcosystemModal();
        });
    }

    const closeFeatureBtn = document.getElementById('closeFeatureModalBtn');
    if (closeFeatureBtn) {
        closeFeatureBtn.addEventListener('click', closeModal);
    }

    const closeEcosystemBtn = document.getElementById('closeEcosystemModalBtn');
    if (closeEcosystemBtn) {
        closeEcosystemBtn.addEventListener('click', closeEcosystemModal);
    }

    // Close on outside click
    window.addEventListener('click', function (event) {
        const featureModal = document.getElementById('featureModal');
        const ecosystemModal = document.getElementById('ecosystemModal');
        if (featureModal && event.target === featureModal) {
            closeModal();
        }
        if (ecosystemModal && event.target === ecosystemModal) {
            closeEcosystemModal();
        }
    });

    // Screenshot Carousel Logic
    const track = document.getElementById('carouselTrack');
    const dotsContainer = document.getElementById('carouselDots');
    const slides = track ? track.querySelectorAll('.carousel-slide') : [];
    const prevBtn = document.querySelector('.carousel-nav.prev');
    const nextBtn = document.querySelector('.carousel-nav.next');

    if (track && slides.length > 0) {
        // Create dot indicators
        slides.forEach((_, index) => {
            const dot = document.createElement('button');
            dot.className = 'carousel-dot' + (index === 0 ? ' active' : '');
            dot.setAttribute('aria-label', `Go to slide ${index + 1}`);
            dot.addEventListener('click', () => scrollToSlide(index));
            dotsContainer.appendChild(dot);
        });

        const dots = dotsContainer.querySelectorAll('.carousel-dot');

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

        // Update active dot on scroll
        function updateActiveDot() {
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
        }

        track.addEventListener('scroll', updateActiveDot);

        // Arrow navigation
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

        // Keyboard navigation for carousel
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') {
                track.scrollBy({ left: -300, behavior: 'smooth' });
            } else if (e.key === 'ArrowRight') {
                track.scrollBy({ left: 300, behavior: 'smooth' });
            }
        });
    }

    // ESC key to close active modals
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeModal();
            closeEcosystemModal();
        }
    });

    // Scroll Reveal Animation (IntersectionObserver)
    const revealElements = document.querySelectorAll('.reveal');

    if (revealElements.length > 0) {
        // Check if user prefers reduced motion
        const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        if (prefersReducedMotion) {
            // Show all elements immediately without animation
            revealElements.forEach(el => {
                el.style.opacity = '1';
                el.style.transform = 'none';
            });
        } else {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        entry.target.classList.add('revealed');
                        observer.unobserve(entry.target); // Only animate once
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
    // Check if mediumZoom is loaded
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
