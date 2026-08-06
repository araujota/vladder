module VLadderJuliaFixture

export count_equal, allocating_copy, unstable_count
export pointwise!, guarded!, stencil!, prefix_scan!, recurrence!, indirect!

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

function pointwise!(dst::Vector{Float32}, src::Vector{Float32})::Nothing
    @inbounds for i in eachindex(src)
        dst[i] = src[i] * src[i] + 0.25f0
    end
    return nothing
end

function guarded!(dst::Vector{Float32}, src::Vector{Float32})::Nothing
    @inbounds for i in eachindex(src)
        x = src[i]
        dst[i] = x > 0.0f0 ? x : 0.0f0
    end
    return nothing
end

function stencil!(dst::Vector{Float32}, src::Vector{Float32})::Nothing
    @inbounds for i in eachindex(src)
        if i == firstindex(src) || i == lastindex(src)
            dst[i] = src[i]
        else
            dst[i] = src[i - 1] * 0.25f0 + src[i] * 0.5f0 + src[i + 1] * 0.25f0
        end
    end
    return nothing
end

function prefix_scan!(dst::Vector{Float32}, src::Vector{Float32})::Nothing
    sum = 0.0f0
    @inbounds for i in eachindex(src)
        sum += src[i]
        dst[i] = sum
    end
    return nothing
end

function recurrence!(dst::Vector{Float32}, src::Vector{Float32})::Nothing
    y = 0.0f0
    @inbounds for i in eachindex(src)
        y = y * 0.875f0 + src[i] * 0.125f0
        dst[i] = y
    end
    return nothing
end

function indirect!(dst::Vector{Float32}, src::Vector{Float32})::Nothing
    @inbounds for i in eachindex(src)
        j = mod(i * 17, length(src)) + 1
        dst[i] = src[j] * 0.75f0 + src[i] * 0.25f0
    end
    return nothing
end

end
