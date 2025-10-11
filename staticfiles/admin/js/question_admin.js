
(function($) {
    $(document).ready(function() {
        console.log("Question admin script loaded.");
        var questionField = $('#id_depends_on_question');
        var optionField = $('#id_depends_on');
        var optionsUrl = questionField.data('options-url');

        function updateOptionField(questionId, selectedOption) {
            console.log("Updating options for question ID:", questionId);
            if (!questionId) {
                optionField.html('<option value="">---------</option>');
                return;
            }
            $.ajax({
                url: optionsUrl,
                data: {
                    'question_id': questionId
                },
                success: function(data) {
                    console.log("AJAX success. Received data:", data);
                    var options = '<option value="">---------</option>';
                    $.each(data, function(key, value) {
                        options += '<option value="' + key + '">' + value + '</option>';
                    });
                    optionField.html(options);
                    if (selectedOption) {
                        optionField.val(selectedOption);
                    }
                },
                error: function(xhr, status, error) {
                    console.error("AJAX error:", status, error);
                }
            });
        }

        questionField.on('change', function() {
            updateOptionField($(this).val(), null);
        });

        // On page load, if a question is already selected, trigger the update
        if (questionField.val()) {
            updateOptionField(questionField.val(), optionField.val());
        }
    });
})(django.jQuery);
