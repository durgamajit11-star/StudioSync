(function () {
    const MAX_UPLOAD_BYTES = 3.25 * 1024 * 1024;

    const profileForm = document.getElementById('studioProfileForm');
    if (!profileForm) {
        return;
    }

    const editBtn = document.getElementById('editStudioProfileBtn');
    const cancelBtn = document.getElementById('resetBtn');
    const saveBtn = document.getElementById('saveBtn');
    const profileDisplay = document.getElementById('studioProfileDisplay');
    const profileEditor = document.getElementById('studioProfileEditor');
    const statusEl = document.getElementById('profileFormState');

    const serviceList = document.getElementById('servicesContainer');
    const addServiceBtn = document.getElementById('addServiceBtn');

    const avatarInput = document.getElementById('id_profile_image');
    const avatarPreview = document.getElementById('avatarPreview');
    const avatarTriggerBtn = document.getElementById('triggerAvatarUpload');
    const coverInput = document.getElementById('studioCoverInput');
    const coverPreview = document.getElementById('studioCoverPreview');

    const prefSaveBtn = document.getElementById('savePreferencesBtn');
    const prefState = document.getElementById('prefStateText');

    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';

    const logoutAllBtn = document.getElementById('logoutAllBtn');
    const deleteAccountBtn = document.getElementById('deleteAccountBtn');
    const dangerAcknowledge = document.getElementById('dangerAcknowledge');
    const deleteConfirmInput = document.getElementById('deleteConfirmInput');

    const initialFormData = new FormData(profileForm);

    function cloneFormData(source) {
        const cloned = new FormData();
        source.forEach(function (value, key) {
            cloned.append(key, value);
        });
        return cloned;
    }

    function collectSelectedFiles() {
        const uploads = [];
        Array.from(profileForm.querySelectorAll('input[type="file"]')).forEach(function (input) {
            if (!input.files || !input.files.length) {
                return;
            }

            Array.from(input.files).forEach(function (file) {
                uploads.push({ input: input, file: file });
            });
        });
        return uploads;
    }

    function getFileLabel(input) {
        if (!input || !input.name) {
            return 'File';
        }

        const friendlyNames = {
            profile_image: 'Profile image',
            studio_license: 'License document',
            studio_portfolio: 'Portfolio document',
            studio_cover_image: 'Studio cover image'
        };

        return friendlyNames[input.name] || 'File';
    }

    function showStatus(message, tone) {
        if (!statusEl) {
            return;
        }

        statusEl.textContent = message;
        statusEl.classList.remove('text-success', 'text-danger', 'text-warning', 'text-muted');
        statusEl.classList.add(tone || 'text-muted');
    }

    function setEditMode(enabled) {
        if (!profileDisplay || !profileEditor) {
            return;
        }

        profileDisplay.style.display = enabled ? 'none' : 'grid';
        profileEditor.classList.toggle('active', enabled);
    }

    function resetFormToInitial() {
        Array.from(profileForm.elements).forEach(function (el) {
            if (!el.name || !initialFormData.has(el.name)) {
                return;
            }

            if (el.type === 'checkbox') {
                el.checked = initialFormData.getAll(el.name).includes(el.value);
            } else if (el.type !== 'file') {
                el.value = initialFormData.get(el.name) || '';
            }
        });
    }

    function updateImagePreview(inputEl, previewEl) {
        if (!inputEl || !previewEl || !inputEl.files || !inputEl.files[0]) {
            return;
        }

        const reader = new FileReader();
        reader.onload = function (e) {
            previewEl.src = e.target.result;
        };
        reader.readAsDataURL(inputEl.files[0]);
    }

    function createServiceRow(name, description, price) {
        const row = document.createElement('div');
        row.className = 'service-row';
        row.innerHTML = [
            '<div class="row g-2 align-items-end">',
            '<div class="col-md-4">',
            '<label class="form-label mb-1">Service Name</label>',
            `<input type="text" class="form-control" name="service_name[]" value="${name || ''}" placeholder="Wedding Shoot">`,
            '</div>',
            '<div class="col-md-3">',
            '<label class="form-label mb-1">Price (Rs.)</label>',
            `<input type="number" class="form-control" step="0.01" min="0" name="service_price[]" value="${price || ''}" placeholder="2500">`,
            '</div>',
            '<div class="col-md-4">',
            '<label class="form-label mb-1">Description</label>',
            `<input type="text" class="form-control" name="service_description[]" value="${description || ''}" placeholder="2-hour package">`,
            '</div>',
            '<div class="col-md-1 d-grid">',
            '<button type="button" class="btn btn-outline-danger btn-sm remove-service-btn" title="Remove service">',
            '<i class="bi bi-trash"></i>',
            '</button>',
            '</div>',
            '</div>'
        ].join('');
        return row;
    }

    function setSectionExpanded(card, body, button, expanded) {
        if (!card || !body || !button) {
            return;
        }

        const icon = button.querySelector('i');
        card.classList.toggle('is-collapsed', !expanded);
        body.hidden = !expanded;
        button.setAttribute('aria-expanded', String(expanded));

        if (icon) {
            icon.className = expanded ? 'bi bi-chevron-up' : 'bi bi-chevron-down';
        }
    }

    function setupSectionToggles() {
        const toggleButtons = document.querySelectorAll('[data-toggle-card]');

        toggleButtons.forEach(function (button) {
            const targetId = button.getAttribute('data-target');
            const body = targetId ? document.getElementById(targetId) : null;
            const card = button.closest('.profile-card');
            const initiallyExpanded = button.getAttribute('aria-expanded') === 'true';

            if (!card || !body) {
                return;
            }

            setSectionExpanded(card, body, button, initiallyExpanded);

            button.addEventListener('click', function () {
                const expanded = button.getAttribute('aria-expanded') === 'true';
                setSectionExpanded(card, body, button, !expanded);
            });
        });
    }

    function updateDangerActionsState() {
        const acknowledged = !!dangerAcknowledge?.checked;
        const deleteConfirmed = (deleteConfirmInput?.value || '').trim().toUpperCase() === 'DELETE';

        if (logoutAllBtn) {
            logoutAllBtn.disabled = !acknowledged;
        }

        if (deleteAccountBtn) {
            deleteAccountBtn.disabled = !(acknowledged && deleteConfirmed);
        }
    }

    if (editBtn) {
        editBtn.addEventListener('click', function () {
            setEditMode(true);
            showStatus('Edit mode enabled.', 'text-warning');
        });
    }

    if (cancelBtn) {
        cancelBtn.addEventListener('click', function () {
            profileForm.reset();
            resetFormToInitial();
            setEditMode(false);
            showStatus('Changes discarded.', 'text-muted');
        });
    }

    if (serviceList) {
        serviceList.addEventListener('click', function (event) {
            const target = event.target.closest('.remove-service-btn');
            if (!target) {
                return;
            }

            const row = target.closest('.service-row');
            if (!row) {
                return;
            }

            if (serviceList.querySelectorAll('.service-row').length <= 1) {
                const nameInput = row.querySelector('input[name="service_name[]"]');
                const descInput = row.querySelector('input[name="service_description[]"]');
                const priceInput = row.querySelector('input[name="service_price[]"]');
                if (nameInput) nameInput.value = '';
                if (descInput) descInput.value = '';
                if (priceInput) priceInput.value = '';
                return;
            }

            row.remove();
        });
    }

    if (addServiceBtn && serviceList) {
        addServiceBtn.addEventListener('click', function () {
            serviceList.appendChild(createServiceRow('', '', ''));
        });
    }

    if (avatarInput) {
        avatarInput.addEventListener('change', function () {
            updateImagePreview(avatarInput, avatarPreview);
        });
    }

    if (avatarTriggerBtn && avatarInput) {
        avatarTriggerBtn.addEventListener('click', function () {
            avatarInput.click();
        });
    }

    if (coverInput) {
        coverInput.addEventListener('change', function () {
            updateImagePreview(coverInput, coverPreview);
            if (coverPreview) {
                coverPreview.classList.remove('d-none');
            }
        });
    }

    if (prefSaveBtn) {
        prefSaveBtn.addEventListener('click', function () {
            prefSaveBtn.disabled = true;
            if (prefState) {
                prefState.textContent = 'Saving preferences...';
            }

            const payload = {
                email_notifications: !!document.getElementById('prefEmail')?.checked,
                sms_alerts: !!document.getElementById('prefSms')?.checked,
                portfolio_visibility: !!document.getElementById('prefVisibility')?.checked,
                marketing_emails: !!document.getElementById('prefMarketing')?.checked,
                two_factor_enabled: !!document.getElementById('twoFactorToggle')?.checked,
                device_login_alerts: !!document.getElementById('deviceAlertToggle')?.checked
            };

            fetch('/dashboard/studio/profile/preferences/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(payload)
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (prefState) {
                        prefState.textContent = data.message || 'Preferences saved.';
                    }
                })
                .catch(function () {
                    if (prefState) {
                        prefState.textContent = 'Unable to save preferences now. Try again.';
                    }
                })
                .finally(function () {
                    prefSaveBtn.disabled = false;
                });
        });
    }

    if (logoutAllBtn) {
        logoutAllBtn.addEventListener('click', function () {
            if (logoutAllBtn.disabled) {
                return;
            }

            if (!window.confirm('Sign out from all devices?')) {
                return;
            }

            fetch('/dashboard/studio/profile/logout-all/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    alert(data.message || 'Signed out from all devices.');
                })
                .catch(function () {
                    alert('Could not complete this action right now.');
                });
        });
    }

    if (deleteAccountBtn) {
        deleteAccountBtn.addEventListener('click', function () {
            if (deleteAccountBtn.disabled) {
                return;
            }

            if (!window.confirm('Delete account permanently? This cannot be undone.')) {
                return;
            }

            fetch('/dashboard/studio/profile/delete-account/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken,
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    if (data && data.redirect_url) {
                        window.location.href = data.redirect_url;
                        return;
                    }
                    alert(data.message || 'Account deleted.');
                })
                .catch(function () {
                    alert('Could not delete account right now.');
                });
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', function () {
            showStatus('Saving profile changes...', 'text-warning');
        });
    }

    profileForm.addEventListener('submit', async function (event) {
        const uploads = collectSelectedFiles();
        if (!uploads.length) {
            return;
        }

        event.preventDefault();

        const originalButtonText = saveBtn ? saveBtn.innerHTML : '';
        if (saveBtn) {
            saveBtn.disabled = true;
        }

        try {
            const baseFormData = new FormData(profileForm);
            Array.from(profileForm.querySelectorAll('input[type="file"]')).forEach(function (input) {
                if (input.name) {
                    baseFormData.delete(input.name);
                }
            });

            for (let index = 0; index < uploads.length; index += 1) {
                const upload = uploads[index];
                if (upload.file.size > MAX_UPLOAD_BYTES) {
                    throw new Error(getFileLabel(upload.input) + ' must be under 3.25 MB. Please choose a smaller file.');
                }

                showStatus('Uploading ' + getFileLabel(upload.input) + ' ' + (index + 1) + ' of ' + uploads.length + '...', 'text-warning');

                const requestData = cloneFormData(baseFormData);
                requestData.append(upload.input.name, upload.file, upload.file.name);

                const response = await fetch(profileForm.action || window.location.href, {
                    method: 'POST',
                    body: requestData,
                    credentials: 'same-origin',
                    headers: {
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                });

                if (!response.ok) {
                    throw new Error('Unable to save profile changes. Please try again.');
                }
            }

            showStatus('Profile updated successfully. Reloading...', 'text-success');
            window.location.reload();
        } catch (error) {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalButtonText;
            }
            showStatus(error.message || 'Unable to save profile changes right now.', 'text-danger');
            alert(error.message || 'Unable to save profile changes right now.');
        }
    });

    if (dangerAcknowledge) {
        dangerAcknowledge.addEventListener('change', updateDangerActionsState);
    }

    if (deleteConfirmInput) {
        deleteConfirmInput.addEventListener('input', updateDangerActionsState);
    }

    showStatus('Profile loaded. Use Edit to make changes.', 'text-muted');
    setEditMode(false);
    updateDangerActionsState();
    setupSectionToggles();
})();
