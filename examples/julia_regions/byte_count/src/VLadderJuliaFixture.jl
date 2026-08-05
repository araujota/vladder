module VLadderJuliaFixture

export count_equal, allocating_copy, unstable_count

function count_equal(bytes::Vector{UInt8}, needle::UInt8)::Int
    count = 0
    @inbounds for value in bytes
        count += value == needle
    end
    return count
end

function allocating_copy(bytes::Vector{UInt8}, needle::UInt8)::Int
    owned = copy(bytes)
    return count(==(needle), owned)
end

function unstable_count(bytes::Vector{UInt8}, needle::UInt8)
    count = rand(Bool) ? 0 : 0.0
    for value in bytes
        count += value == needle
    end
    return count
end

end
