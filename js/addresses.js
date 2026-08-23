const ADDRESS_API = "/address";
const PINCODE_API = "https://api.postalpincode.in/pincode";

let editingAddressId = null;
let deleteAddressId = null;
let pinRequest = null;

const addressListEl = document.getElementById("address-list");
const addressModal = document.getElementById("address-modal");
const mainHeader = document.getElementById("main-header");
const addressForm = document.getElementById("address-form");
const postalCodeInput = document.getElementById("postal_code");
const cityInput = document.getElementById("city");
const stateInput = document.getElementById("state");
const countryInput = document.getElementById("country");
const postalError = document.getElementById("postal-error");

const fullNameInput = document.getElementById("full_name");
const phoneInput = document.getElementById("phone_number");
const alternatePhoneInput = document.getElementById("alternate_phone");
const addressInput = document.getElementById("address");
const landmarkInput = document.getElementById("landmark");
const addressTypeSelect = document.getElementById("address_type");
const isDefaultCheckbox = document.getElementById("is_default");
const deliveryInstructionsInput = document.getElementById("delivery_instructions");
const addressModalLabel = document.getElementById("address-modal-label");
const addressModalTitle = document.getElementById("address-modal-title");
const addressModalDescription = document.getElementById("address-modal-description");
const submitBtn = document.getElementById("address-submit-btn");

function showToast(title, message, type = "info") {
    const toast = document.getElementById("auth-toast");
    if (!toast) return;

    const toastTitle = document.getElementById("toast-title");
    const toastMessage = document.getElementById("toast-message");
    const toastIconSuccess = document.getElementById("toast-icon-success");
    const toastIconInfo = document.getElementById("toast-icon-info");
    const toastIcon = document.getElementById("toast-icon");

    if (toastTitle) toastTitle.textContent = title;
    if (toastMessage) toastMessage.textContent = message;

    if (type === "success") {
        if (toastIconSuccess) toastIconSuccess.classList.remove("hidden");
        if (toastIconInfo) toastIconInfo.classList.add("hidden");
        if (toast) toast.style.borderLeftColor = "#16a34a";
        if (toastIcon) toastIcon.style.background = "#f0fdf4";
    } else {
        if (toastIconSuccess) toastIconSuccess.classList.add("hidden");
        if (toastIconInfo) toastIconInfo.classList.remove("hidden");
        if (toast) toast.style.borderLeftColor = "#6b7280";
        if (toastIcon) toastIcon.style.background = "#f9fafb";
    }

    toast.classList.remove("hidden", "translate-x-full", "opacity-0");
    toast.classList.add("translate-x-0", "opacity-100");

    setTimeout(() => {
        toast.classList.remove("translate-x-0", "opacity-100");
        toast.classList.add("translate-x-full", "opacity-0");
        setTimeout(() => {
            toast.classList.add("hidden");
        }, 300);
    }, 3000);
}

function formatDate(dateString) {
    if (!dateString) return "";
    const date = new Date(dateString);
    return date.toLocaleDateString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
    });
}

function getInitials(name) {
    if (!name) return "";
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name.substring(0, 2).toUpperCase();
}

function openAddressModal(address = null) {
    if (address) {
        editingAddressId = address.id;

        fullNameInput.value = address.full_name || "";
        phoneInput.value = address.phone_number || "";
        alternatePhoneInput.value = address.alternate_phone || "";
        addressInput.value = address.address || "";
        landmarkInput.value = address.landmark || "";
        postalCodeInput.value = address.postal_code || "";
        cityInput.value = address.city || "";
        stateInput.value = address.state || "";
        countryInput.value = address.country || "India";
        addressTypeSelect.value = address.address_type || "home";
        isDefaultCheckbox.checked = address.is_default || false;
        deliveryInstructionsInput.value = address.delivery_instructions || "";

        cityInput.readOnly = true;
        stateInput.readOnly = true;
        countryInput.readOnly = true;
        cityInput.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");
        stateInput.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");
        countryInput.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");

        postalError.classList.add("hidden");
        postalError.textContent = "";

        if (addressModalLabel) addressModalLabel.textContent = "Edit Address";
        if (addressModalTitle) addressModalTitle.textContent = "Update Delivery Address";
        if (addressModalDescription) addressModalDescription.textContent = "Update your existing delivery address.";
        if (submitBtn) submitBtn.textContent = "Update Address";
    } else {
        editingAddressId = null;
        resetForm();

        if (addressModalLabel) addressModalLabel.textContent = "New Address";
        if (addressModalTitle) addressModalTitle.textContent = "Add Delivery Address";
        if (addressModalDescription) addressModalDescription.textContent = "Add a new address for your future deliveries.";
        if (submitBtn) submitBtn.textContent = "Save Address";
    }

    addressModal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
    mainHeader.classList.add("modal-hidden");
}

function closeAddressModal() {
    addressModal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    mainHeader.classList.remove("modal-hidden");
    resetForm();
}

function resetForm() {
    addressForm.reset();
    editingAddressId = null;
    cityInput.value = "";
    stateInput.value = "";
    countryInput.value = "";
    postalError.classList.add("hidden");
    postalError.textContent = "";

    [cityInput, stateInput, countryInput].forEach((input) => {
        input.readOnly = true;
        input.placeholder = "Enter PIN code first";
        input.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");
    });
}

async function fetchAddresses() {
    try {
        const response = await window.auth.authFetch(ADDRESS_API);
        if (!response.ok) {
            throw new Error("Failed to fetch addresses");
        }
        const addresses = await response.json();
        renderAddresses(addresses);
    } catch (error) {
        console.error("Error fetching addresses:", error);
        showToast("Error", "Failed to load addresses. Please try again.", "info");
    }
}

function renderAddresses(addresses) {
    if (!addressListEl) return;

    if (addresses.length === 0) {
        addressListEl.innerHTML = `
            <div class="col-span-full flex flex-col items-center justify-center py-16 text-center">
                <svg class="h-12 w-12 text-black/20 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 21s7-5.2 7-11a7 7 0 10-14 0c0 5.8 7 11 7 11z" />
                    <circle cx="12" cy="10" r="2.2" />
                </svg>
                <p class="text-sm text-black/50">No addresses saved yet.</p>
                <p class="text-xs text-black/35 mt-1">Click "Add New Address" to get started.</p>
            </div>
        `;
        return;
    }

    addressListEl.innerHTML = addresses
        .map(
            (addr) => {
                const isDefault = addr.is_default;
                const typeLabel = addr.address_type
                    ? addr.address_type.charAt(0).toUpperCase() + addr.address_type.slice(1)
                    : "Other";

                return `
                <article class="group relative border border-black/10 bg-white p-6 transition duration-300 hover:border-black/25" data-address-id="${addr.id}">
                    <div class="flex items-start justify-between gap-5">
                        <div class="flex items-center gap-4">
                            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-full ${isDefault ? "bg-black text-sm font-medium text-white" : "border border-black/10 text-sm font-medium"}">
                                ${getInitials(addr.full_name)}
                            </div>
                            <div>
                                <h2 class="text-base font-semibold tracking-tight">${escapeHtml(addr.full_name)}</h2>
                                <p class="mt-1 text-sm text-black/50">${escapeHtml(addr.phone_number)}</p>
                            </div>
                        </div>
                        ${isDefault ? `<span class="inline-flex items-center gap-1.5 border border-black bg-black px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.15em] text-white">
                            <span class="h-1.5 w-1.5 rounded-full bg-white"></span> Default
                        </span>` : ""}
                    </div>

                    <div class="mt-7 border-t border-black/10 pt-6">
                        <div class="flex gap-4">
                            <div class="mt-0.5 shrink-0">
                                <svg class="h-5 w-5 text-black/70" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.6">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M12 21s7-5.2 7-11a7 7 0 10-14 0c0 5.8 7 11 7 11z" />
                                    <circle cx="12" cy="10" r="2.2" />
                                </svg>
                            </div>
                            <div class="text-sm leading-6 text-black/70">
                                <p>${escapeHtml(addr.address)}${addr.landmark ? `, ${escapeHtml(addr.landmark)}` : ""}</p>
                                <p>${escapeHtml(addr.city)}, ${escapeHtml(addr.state)} — ${escapeHtml(addr.postal_code)}</p>
                                <p>${escapeHtml(addr.country)}</p>
                            </div>
                        </div>
                    </div>

                    <div class="mt-6">
                        <span class="inline-flex items-center border border-black/10 px-3 py-1.5 text-[10px] font-medium uppercase tracking-[0.18em] text-black/55">
                            ${typeLabel}
                        </span>
                    </div>

                    <div class="mt-7 flex items-center justify-between border-t border-black/10 pt-5">
                        <button type="button" onclick="addressesJS.editAddress(${addr.id})" class="text-xs font-medium uppercase tracking-[0.12em] text-black/50 transition hover:text-black">Edit</button>
                        <div class="flex items-center gap-5">
                            <button type="button" onclick="addressesJS.deleteAddress(${addr.id})" class="text-xs font-medium uppercase tracking-[0.12em] text-black/50 transition hover:text-black">Delete</button>
                            ${!isDefault ? `<button type="button" onclick="addressesJS.makeDefault(${addr.id})" class="text-xs font-medium uppercase tracking-[0.12em] text-black transition hover:opacity-50">Make Default</button>` : ""}
                        </div>
                    </div>
                </article>
                `;
            }
        )
        .join("");
}

function escapeHtml(text) {
    if (!text) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

async function handleFormSubmit(e) {
    e.preventDefault();

    if (!fullNameInput.value.trim()) {
        showToast("Validation Error", "Full name is required.", "info");
        return;
    }

    if (!/^\d{10}$/.test(phoneInput.value.trim())) {
        showToast("Validation Error", "Phone number must be exactly 10 digits.", "info");
        return;
    }

    if (alternatePhoneInput.value && !/^\d{10}$/.test(alternatePhoneInput.value.trim())) {
        showToast("Validation Error", "Alternate phone must be exactly 10 digits.", "info");
        return;
    }

    if (!addressInput.value.trim() || addressInput.value.trim().length < 5) {
        showToast("Validation Error", "Address must be at least 5 characters.", "info");
        return;
    }

    if (!postalCodeInput.value || !/^\d{6}$/.test(postalCodeInput.value)) {
        showToast("Validation Error", "Please enter a valid 6-digit PIN code.", "info");
        return;
    }

    const payload = {
        full_name: fullNameInput.value.trim(),
        phone_number: phoneInput.value.trim(),
        alternate_phone: alternatePhoneInput.value.trim() || null,
        address: addressInput.value.trim(),
        landmark: landmarkInput.value.trim() || null,
        city: cityInput.value.trim(),
        state: stateInput.value.trim(),
        country: countryInput.value.trim() || "India",
        postal_code: postalCodeInput.value.trim(),
        address_type: addressTypeSelect.value,
        delivery_instructions: deliveryInstructionsInput.value.trim() || null,
        is_default: isDefaultCheckbox.checked,
    };

    const submitBtn = addressForm.querySelector('button[type="submit"]');
    const originalText = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = "Saving...";

    try {
        let response;
        if (editingAddressId) {
            response = await window.auth.authFetch(`${ADDRESS_API}/${editingAddressId}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
        } else {
            response = await window.auth.authFetch(ADDRESS_API, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
        }

        if (response.ok || response.status === 204) {
            showToast(
                "Success",
                editingAddressId ? "Address updated successfully." : "Address added successfully.",
                "success"
            );
            closeAddressModal();
            fetchAddresses();
        } else {
            const data = await response.json().catch(() => ({}));
            const errorMsg = data.detail || data.message || "Failed to save address.";
            showToast("Error", errorMsg, "info");
        }
    } catch (error) {
        console.error("Error saving address:", error);
        showToast("Error", "Something went wrong. Please try again.", "info");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = originalText;
    }
}

async function editAddress(addressId) {
    try {
        const response = await window.auth.authFetch(`${ADDRESS_API}/${addressId}`);
        if (!response.ok) {
            throw new Error("Failed to fetch address");
        }
        const address = await response.json();
        openAddressModal(address);
    } catch (error) {
        console.error("Error fetching address:", error);
        showToast("Error", "Failed to load address details.", "info");
    }
}

async function deleteAddress(addressId) {
    deleteAddressId = addressId;
    openDeleteModal();
}

function openDeleteModal() {
    const deleteModal = document.getElementById("delete-modal");
    if (!deleteModal) return;
    deleteModal.classList.remove("hidden");
    deleteModal.style.display = "block";
    document.body.classList.add("overflow-hidden");
    mainHeader.classList.add("modal-hidden");
}

function closeDeleteModal() {
    const deleteModal = document.getElementById("delete-modal");
    if (!deleteModal) return;
    deleteModal.classList.add("hidden");
    deleteModal.style.display = "none";
    document.body.classList.remove("overflow-hidden");
    mainHeader.classList.remove("modal-hidden");
}

async function confirmDelete() {
    if (!deleteAddressId) return;

    const addressId = deleteAddressId;
    closeDeleteModal();

    try {
        const response = await window.auth.authFetch(`${ADDRESS_API}/${addressId}`, {
            method: "DELETE",
        });

        if (response.ok || response.status === 204) {
            showToast("Success", "Address deleted successfully.", "success");
            fetchAddresses();
        } else {
            const data = await response.json().catch(() => ({}));
            const errorMsg = data.detail || data.message || "Failed to delete address.";
            showToast("Error", errorMsg, "info");
        }
    } catch (error) {
        console.error("Error deleting address:", error);
        showToast("Error", "Something went wrong. Please try again.", "info");
    } finally {
        deleteAddressId = null;
    }
}

async function makeDefault(addressId) {
    try {
        const response = await window.auth.authFetch(`${ADDRESS_API}/${addressId}/default`, {
            method: "PATCH",
        });

        if (response.ok) {
            const data = await response.json().catch(() => ({}));
            showToast("Success", data.message || "Default address updated.", "success");
            fetchAddresses();
        } else {
            const data = await response.json().catch(() => ({}));
            const errorMsg = data.detail || data.message || "Failed to update default address.";
            showToast("Error", errorMsg, "info");
        }
    } catch (error) {
        console.error("Error updating default address:", error);
        showToast("Error", "Something went wrong. Please try again.", "info");
    }
}

postalCodeInput.addEventListener("input", async function () {
    this.value = this.value.replace(/\D/g, "").slice(0, 6);

    cityInput.value = "";
    stateInput.value = "";
    countryInput.value = "";

    postalError.classList.add("hidden");
    postalError.textContent = "";

    if (this.value.length !== 6) {
        return;
    }

    cityInput.placeholder = "Loading...";
    stateInput.placeholder = "Loading...";
    countryInput.placeholder = "Loading...";

    try {
        if (pinRequest) {
            pinRequest.abort();
        }
        const controller = new AbortController();
        pinRequest = controller;

        const response = await fetch(`${PINCODE_API}/${this.value}`, {
            signal: controller.signal,
        });

        pinRequest = null;

        if (!response.ok) {
            throw new Error("PIN lookup failed");
        }

        const data = await response.json();

        if (
            !data ||
            data[0].Status !== "Success" ||
            !data[0].PostOffice ||
            data[0].PostOffice.length === 0
        ) {
            throw new Error("Invalid PIN code");
        }

        const location = data[0].PostOffice[0];

        cityInput.value = location.District || location.Block || "";
        stateInput.value = location.State || "";
        countryInput.value = location.Country || "India";

        cityInput.placeholder = "City";
        stateInput.placeholder = "State";
        countryInput.placeholder = "Country";

        cityInput.readOnly = true;
        stateInput.readOnly = true;
        countryInput.readOnly = true;
        cityInput.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");
        stateInput.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");
        countryInput.classList.add("cursor-not-allowed", "bg-black/[0.03]", "text-black/60");
    } catch (error) {
        if (error.name === "AbortError") return;

        cityInput.value = "";
        stateInput.value = "";
        countryInput.value = "";

        cityInput.placeholder = "Enter a valid PIN code";
        stateInput.placeholder = "Enter a valid PIN code";
        countryInput.placeholder = "Enter a valid PIN code";

        postalError.textContent = "Please enter a valid PIN code.";
        postalError.classList.remove("hidden");
    }
});

addressForm.addEventListener("submit", handleFormSubmit);

document.addEventListener("DOMContentLoaded", () => {
    fetchAddresses();
});

window.addressesJS = {
    openAddressModal,
    closeAddressModal,
    openDeleteModal,
    closeDeleteModal,
    confirmDelete,
    editAddress,
    deleteAddress,
    makeDefault,
};
