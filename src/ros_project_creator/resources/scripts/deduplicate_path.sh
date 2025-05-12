#!/bin/bash

# Safely print the input string (passed as $1)
# This ensures that any special characters in the input are handled correctly.
printf '%s\n' "$1" |

# Replace each colon with a newline to split the input into individual tokens.
tr ':' '\n' |

# Sort the tokens in reverse order, assuming duplicates appears to the left, for example
# PATH= ~/.local/bin:/usr/bin:/bin
# PATH="/bin:${PATH}" => /bin is duplicated to the left.
tac |

# Use awk to trim each token, remove empty tokens, and filter out duplicates.
awk '
# Function: trim
# Removes leading and trailing whitespace (spaces and tabs) from the input string.
function trim(s) {
    gsub(/^[ \t]+|[ \t]+$/, "", s)
    return s
}
{
    # Apply the trim function to the current token.
    token = trim($0)

    # If the token is not empty and has not been seen before, print it.
    if (token != "" && !seen[token]++) {
    print token
    }
}
' |

# Reverse again to conserve original order
tac |

# Join the resulting tokens into a single line separated by colons.
paste -sd ':'


